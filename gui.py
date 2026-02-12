import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
from main import run_diastasis, save_layers_to_files
from graph_solver import GraphSolver
from cairosvg import svg2png
from PIL import Image, ImageTk
import io
import os

class DiastasisGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Mozaix Diastasis")
        self.root.geometry("1200x800")

        self.filepath = ""
        self.algorithm = tk.StringVar(value="DSATUR")
        self.use_optimizer = tk.BooleanVar(value=False)
        self.num_layers = tk.IntVar(value=3)
        self.shapes = None
        self.coloring = None
        self.original_image = None
        self.svg_width = 0
        self.svg_height = 0

        # Create and pack the widgets
        self.create_widgets()

    def create_widgets(self):
        # Main frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left frame for controls
        left_frame = tk.Frame(main_frame, width=450)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        left_frame.pack_propagate(False)

        # Right frame for preview
        right_frame = tk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # --- Left Frame Widgets ---

        # Frame for file selection
        file_frame = tk.Frame(left_frame, pady=10)
        file_frame.pack(fill=tk.X)

        self.select_button = tk.Button(file_frame, text="Select SVG", command=self.select_file)
        self.select_button.pack(side=tk.LEFT, padx=10)

        self.filepath_label = tk.Label(file_frame, text="No file selected", wraplength=300, justify=tk.LEFT)
        self.filepath_label.pack(side=tk.LEFT)

        # Frame for algorithm selection
        algo_frame = tk.Frame(left_frame, pady=5)
        algo_frame.pack(fill=tk.X)

        algo_label = tk.Label(algo_frame, text="Algorithm:")
        algo_label.pack(side=tk.LEFT, padx=10)

        self.algo_combobox = ttk.Combobox(
            algo_frame,
            textvariable=self.algorithm,
            values=GraphSolver.AVAILABLE_ALGORITHMS,
            state="readonly"
        )
        self.algo_combobox.pack(side=tk.LEFT)
        self.algo_combobox.bind("<<ComboboxSelected>>", self.on_algo_change)

        # Frame for number of layers (for force_k)
        self.num_layers_frame = tk.Frame(left_frame, pady=5)
        
        num_layers_label = tk.Label(self.num_layers_frame, text="Number of Layers:")
        num_layers_label.pack(side=tk.LEFT, padx=10)
        
        self.num_layers_entry = tk.Entry(self.num_layers_frame, textvariable=self.num_layers, width=5)
        self.num_layers_entry.pack(side=tk.LEFT)
        
        # Initially hide the num_layers frame
        self.num_layers_frame.pack_forget()

        # Optimizer checkbox
        optimizer_frame = tk.Frame(left_frame, pady=5)
        optimizer_frame.pack(fill=tk.X, padx=10)
        self.optimizer_check = tk.Checkbutton(
            optimizer_frame,
            text="Apply post-processing optimization (slower)",
            variable=self.use_optimizer
        )
        self.optimizer_check.pack(anchor=tk.W)

        # Algorithm explanations
        explanation_frame = tk.LabelFrame(left_frame, text="Algorithm Guide", pady=5, padx=5)
        explanation_frame.pack(fill=tk.X, pady=10)

        explanations = {
            "largest_first": "(Welsh-Powell) Fast. Good starting point. Colors nodes with the most neighbors first.",
            "DSATUR": "Good balance of speed and quality. Prioritizes nodes with the most distinctly colored neighbors.",
            "independent_set": "Potentially very high quality. Finds groups of non-overlapping shapes to color at once.",
            "smallest_last": "Good quality. Colors nodes in reverse order of their removal in a graph simplification process.",
            "random_sequential": "Fastest, but least optimal. Colors nodes in a random order.",
            "connected_sequential_bfs": "Colors nodes based on a Breadth-First Search traversal.",
            "connected_sequential_dfs": "Colors nodes based on a Depth-First Search traversal.",
            "force_k": "Forces the output to a specific number of layers, minimizing overlap."
        }

        for algo, explanation in explanations.items():
            tk.Label(explanation_frame, text=f"- {algo}: {explanation}", wraplength=400, justify=tk.LEFT).pack(anchor=tk.W)

        # Frame for processing
        process_frame = tk.Frame(left_frame, pady=10)
        process_frame.pack(fill=tk.X)

        self.process_button = tk.Button(process_frame, text="Process", command=self.process_file, font=("Helvetica", 12, "bold"))
        self.process_button.pack()

        # Progress bar
        self.progress = ttk.Progressbar(left_frame, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=10, fill=tk.X)

        # Frame for results
        results_frame = tk.LabelFrame(left_frame, text="Results", pady=5, padx=5)
        results_frame.pack(fill=tk.BOTH, expand=True)

        self.results_text = tk.Text(results_frame, height=10, width=50)
        self.results_text.pack(fill=tk.BOTH, expand=True)

        # Frame for saving
        save_frame = tk.Frame(left_frame, pady=10)
        save_frame.pack(fill=tk.X)

        self.save_button = tk.Button(save_frame, text="Save Layers As...", command=self.save_layers, state="disabled")
        self.save_button.pack()

        # --- Right Frame Widgets ---
        self.preview_canvas = tk.Canvas(right_frame, bg="white")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Configure>", self.on_preview_resize)

        self.on_algo_change(None) # Set initial state of the num_layers entry

    def on_algo_change(self, event):
        if self.algorithm.get() == "force_k":
            self.num_layers_frame.pack(fill=tk.X)
        else:
            self.num_layers_frame.pack_forget()

    def select_file(self):
        self.filepath = filedialog.askopenfilename(
            title="Select SVG File",
            filetypes=(("SVG files", "*.svg"), ("All files", "*.*"))
        )
        if self.filepath:
            self.filepath_label.config(text=os.path.basename(self.filepath))
            self.display_preview()
            self.save_button.config(state="disabled")

    def display_preview(self):
        """Display a preview of the selected SVG file, scaled to fit the canvas."""
        try:
            # Get canvas dimensions
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:  # Canvas not ready yet
                self.root.after(100, self.display_preview)  # Try again later
                return
            
            # Convert SVG to PNG for preview - use high resolution for quality
            png_data = svg2png(url=self.filepath, output_width=800, output_height=800)
            image = Image.open(io.BytesIO(png_data))
            
            # Calculate scale factor to fit canvas while maintaining aspect ratio
            img_width, img_height = image.size
            scale_x = canvas_width / img_width
            scale_y = canvas_height / img_height
            scale = min(scale_x, scale_y)  # Use smaller scale to fit entirely
            
            # Calculate new dimensions
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            # Resize image to fit canvas
            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage for tkinter
            self.original_image = ImageTk.PhotoImage(resized_image)
            
            # Clear canvas and display image centered
            self.preview_canvas.delete("all")
            x = canvas_width // 2
            y = canvas_height // 2
            self.preview_canvas.create_image(x, y, image=self.original_image, anchor=tk.CENTER)
            
        except Exception as e:
            print(f"Error displaying preview: {e}")
            self.preview_canvas.delete("all")
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            x = canvas_width // 2 if canvas_width > 1 else 200
            y = canvas_height // 2 if canvas_height > 1 else 200
            self.preview_canvas.create_text(x, y, text="Preview not available", anchor=tk.CENTER)

    def on_preview_resize(self, event):
        """Handle canvas resize events."""
        if self.original_image:
            self.display_preview()

    def process_file(self):
        """Start processing the selected SVG file."""
        if not self.filepath:
            messagebox.showerror("Error", "Please select an SVG file first.")
            return
        
        # Disable the process button and start progress bar
        self.process_button.config(state="disabled")
        self.progress['value'] = 0
        self.progress['maximum'] = 100
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, "Processing...\n")
        
        # Run processing in a separate thread to keep GUI responsive
        thread = threading.Thread(target=self.run_process_thread)
        thread.daemon = True
        thread.start()
        
        # Start progress animation
        self.animate_progress()

    def run_process_thread(self):
        """Run the diastasis processing in a separate thread."""
        try:
            # Get selected algorithm and optimizer setting
            algorithm = self.algorithm.get()
            use_optimizer = self.use_optimizer.get()
            num_layers = None
            if algorithm == "force_k":
                num_layers = self.num_layers.get()
            
            # Run the main processing function
            result = run_diastasis(self.filepath, algorithm=algorithm, use_optimizer=use_optimizer, num_layers=num_layers)
            
            if result and len(result) >= 5:
                self.shapes, self.coloring, summary, self.svg_width, self.svg_height = result
                
                # Update UI in main thread
                self.root.after(0, self.processing_complete, summary)
            else:
                error_msg = result if isinstance(result, str) else "Processing failed with unknown error."
                self.root.after(0, self.processing_error, error_msg)
                
        except Exception as e:
            error_msg = f"Error during processing: {str(e)}"
            self.root.after(0, self.processing_error, error_msg)

    def animate_progress(self):
        """Animate progress bar during processing."""
        if self.process_button['state'] == 'disabled':  # Still processing
            current = self.progress['value']
            if current < 90:  # Don't go to 100% until actually done
                self.progress['value'] = current + 2
            self.root.after(100, self.animate_progress)  # Update every 100ms

    def processing_complete(self, summary):
        """Handle successful processing completion."""
        self.progress['value'] = 100  # Complete the progress bar
        self.process_button.config(state="normal")
        self.save_button.config(state="normal")
        
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, summary)

    def processing_error(self, error_msg):
        """Handle processing errors."""
        self.progress['value'] = 0  # Reset progress bar
        self.process_button.config(state="normal")
        
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, f"Error: {error_msg}")
        
        messagebox.showerror("Processing Error", error_msg)

    def save_layers(self):
        """Save the processed layers to files with user-specified filename."""
        if not self.shapes or not self.coloring:
            messagebox.showerror("Error", "No processed data to save. Please process a file first.")
            return
        
        # Get original filename without extension as default
        original_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        default_filename = f"{original_filename}_layered.svg"
        
        # Ask user for output file path and name
        output_filepath = filedialog.asksaveasfilename(
            title="Save Layered SVG As...",
            defaultextension=".svg",
            filetypes=[("SVG files", "*.svg"), ("All files", "*.*")],
            initialfile=default_filename
        )
        
        if not output_filepath:
            return  # User cancelled
        
        try:
            # Extract directory and filename from the chosen path
            output_dir = os.path.dirname(output_filepath)
            chosen_filename = os.path.basename(output_filepath)
            # Remove extension to get base name for the save function
            base_filename = os.path.splitext(chosen_filename)[0]
            
            # Save layers using the main module function
            save_layers_to_files(self.shapes, self.coloring, output_dir, base_filename, self.svg_width, self.svg_height)
            
            messagebox.showinfo("Success", f"Layered SVG saved successfully as:\n{output_filepath}")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Error saving layers: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = DiastasisGUI(root)
    root.mainloop()