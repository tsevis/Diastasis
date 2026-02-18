import io
import os
import platform
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from cairosvg import svg2png
from PIL import Image, ImageTk

from graph_solver import GraphSolver
from main import run_diastasis, save_layers_to_files, save_single_layer_file


class DiastasisGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Mozaix Diastasis")
        self.root.geometry("1200x800")
        self.root.minsize(1024, 720)

        self.style = ttk.Style(self.root)
        self._appearance = "auto"
        self._theme_mode = "light"

        self.filepath = ""
        self.preview_image = None

        self.algorithm = tk.StringVar(value="DSATUR")
        self.use_optimizer = tk.BooleanVar(value=False)
        self.num_layers = tk.IntVar(value=3)
        self.clip_visible_boundaries = tk.BooleanVar(value=False)
        self.flat_algorithm = tk.StringVar(value="DSATUR")
        self.flat_num_layers = tk.IntVar(value=3)
        self.flat_touch_policy = tk.StringVar(value="No edge/corner touching")
        self.flat_priority_order = tk.StringVar(value="Source order")

        self.results_by_mode = {
            "overlaid": None,
            "flat": None,
        }

        self._setup_theme()
        self.create_widgets()

    def _setup_theme(self):
        system = platform.system().lower()
        if system == "darwin":
            self.style.theme_use("aqua")
        elif system == "windows":
            try:
                self.style.theme_use("vista")
            except tk.TclError:
                self.style.theme_use("default")
        else:
            try:
                self.style.theme_use("clam")
            except tk.TclError:
                self.style.theme_use("default")

    def _theme_colors(self):
        dark = self._theme_mode == "dark"
        return {
            "bg": "#1e1e1e" if dark else "#f5f5f5",
            "fg": "#f2f2f2" if dark else "#1a1a1a",
            "surface": "#2a2a2a" if dark else "#ffffff",
            "active": "#3a3a3a" if dark else "#e8e8e8",
            "canvas": "#b3b3b3" if dark else "white",
            "text_bg": "#2a2a2a" if dark else "#ffffff",
            "text_fg": "#f2f2f2" if dark else "#1a1a1a",
        }

    def _apply_non_macos_theme(self):
        if platform.system() == "Darwin":
            return

        colors = self._theme_colors()

        self.root.configure(bg=colors["bg"])
        self.style.configure(".", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TFrame", background=colors["bg"])
        self.style.configure("TLabel", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TLabelframe", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TCheckbutton", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TButton", background=colors["surface"], foreground=colors["fg"])
        self.style.map("TButton", background=[("active", colors["active"])])
        self.style.configure("TNotebook", background=colors["bg"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=colors["surface"], foreground=colors["fg"])
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", colors["active"])],
            foreground=[("selected", colors["fg"])],
        )

        self.preview_canvas.configure(bg=colors["canvas"])
        self.results_text.configure(bg=colors["text_bg"], fg=colors["text_fg"], insertbackground=colors["text_fg"])

    def toggle_appearance(self):
        if platform.system() == "Darwin":
            try:
                if self._appearance in ("auto", "aqua"):
                    self.root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", ".", "darkaqua")
                    self._appearance = "darkaqua"
                    self._theme_mode = "dark"
                else:
                    self.root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", ".", "aqua")
                    self._appearance = "aqua"
                    self._theme_mode = "light"
            except tk.TclError:
                self._theme_mode = "dark" if self._theme_mode == "light" else "light"
        else:
            self._theme_mode = "dark" if self._theme_mode == "light" else "light"

        self.appearance_btn.config(text="Light Mode" if self._theme_mode == "dark" else "Dark Mode")
        self._apply_non_macos_theme()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(main_frame)
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 0))

        self.appearance_btn = ttk.Button(top_bar, text="Dark Mode", command=self.toggle_appearance)
        self.appearance_btn.pack(side=tk.RIGHT)

        content = ttk.Frame(main_frame)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(content, width=460)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)
        left_frame.pack_propagate(False)

        right_frame = ttk.Frame(content)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        file_frame = ttk.Frame(left_frame)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        self.select_button = ttk.Button(file_frame, text="Select SVG", command=self.select_file)
        self.select_button.pack(side=tk.LEFT)

        self.filepath_label = ttk.Label(file_frame, text="No file selected", width=34)
        self.filepath_label.pack(side=tk.LEFT, padx=(10, 0))

        clip_frame = ttk.Frame(left_frame)
        clip_frame.pack(fill=tk.X, pady=(0, 8))
        self.clip_check = ttk.Checkbutton(
            clip_frame,
            text="Clip Shapes To Visible Boundaries",
            variable=self.clip_visible_boundaries,
        )
        self.clip_check.pack(anchor=tk.W)

        self.mode_notebook = ttk.Notebook(left_frame)
        self.mode_notebook.pack(fill=tk.X)

        self.overlaid_tab = ttk.Frame(self.mode_notebook)
        self.flat_tab = ttk.Frame(self.mode_notebook)
        self.mode_notebook.add(self.overlaid_tab, text="Overlaid Complexity")
        self.mode_notebook.add(self.flat_tab, text="Flat Complexity")
        self.mode_notebook.bind("<<NotebookTabChanged>>", self.on_mode_change)

        self._build_overlaid_tab()
        self._build_flat_tab()

        process_frame = ttk.Frame(left_frame)
        process_frame.pack(fill=tk.X, pady=(10, 0))

        self.process_button = ttk.Button(process_frame, text="Process", command=self.process_file)
        self.process_button.pack(anchor=tk.CENTER)

        self.progress = ttk.Progressbar(left_frame, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(10, 10))

        results_frame = ttk.LabelFrame(left_frame, text="Results")
        results_frame.pack(fill=tk.BOTH, expand=True)

        self.results_text = tk.Text(results_frame, height=11, wrap=tk.WORD)
        self.results_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        save_frame = ttk.Frame(left_frame)
        save_frame.pack(fill=tk.X, pady=(10, 0))

        self.save_button = ttk.Button(save_frame, text="Save Layers As...", command=self.save_layers, state="disabled")
        self.save_button.pack(anchor=tk.CENTER)
        self.save_single_button = ttk.Button(
            save_frame,
            text="Save Clipped 1-Layer As...",
            command=self.save_single_layer,
            state="disabled",
        )
        self.save_single_button.pack(anchor=tk.CENTER, pady=(6, 0))

        self.preview_canvas = tk.Canvas(right_frame, bg="white")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Configure>", self.on_preview_resize)

        self.on_algo_change()
        self._apply_non_macos_theme()

    def _build_overlaid_tab(self):
        algo_frame = ttk.Frame(self.overlaid_tab)
        algo_frame.pack(fill=tk.X, pady=8, padx=4)

        ttk.Label(algo_frame, text="Algorithm:").pack(side=tk.LEFT, padx=(0, 8))

        self.algo_combobox = ttk.Combobox(
            algo_frame,
            textvariable=self.algorithm,
            values=GraphSolver.AVAILABLE_ALGORITHMS,
            state="readonly",
            width=28,
        )
        self.algo_combobox.pack(side=tk.LEFT)
        self.algo_combobox.bind("<<ComboboxSelected>>", lambda _evt: self.on_algo_change())

        self.num_layers_frame = ttk.Frame(self.overlaid_tab)
        ttk.Label(self.num_layers_frame, text="Number of Layers:").pack(side=tk.LEFT, padx=(0, 8))
        self.num_layers_entry = ttk.Entry(self.num_layers_frame, textvariable=self.num_layers, width=6)
        self.num_layers_entry.pack(side=tk.LEFT)

        optimizer_frame = ttk.Frame(self.overlaid_tab)
        optimizer_frame.pack(fill=tk.X, padx=4, pady=(0, 8))
        self.optimizer_check = ttk.Checkbutton(
            optimizer_frame,
            text="Apply post-processing optimization (slower)",
            variable=self.use_optimizer,
        )
        self.optimizer_check.pack(anchor=tk.W)

        explanation_frame = ttk.LabelFrame(self.overlaid_tab, text="Algorithm Guide")
        explanation_frame.pack(fill=tk.X, padx=4, pady=(0, 6))

        explanations = {
            "largest_first": "(Welsh-Powell) Fast. Colors nodes with the most neighbors first.",
            "DSATUR": "Good balance of speed and quality. Prioritizes high saturation nodes.",
            "independent_set": "Potentially high quality. Finds non-overlapping groups first.",
            "smallest_last": "Good quality. Colors in reverse simplification order.",
            "random_sequential": "Fastest, but least optimal.",
            "connected_sequential_bfs": "Breadth-first traversal coloring.",
            "connected_sequential_dfs": "Depth-first traversal coloring.",
            "force_k": "Forces a specific number of layers minimizing overlap.",
        }

        for algo, explanation in explanations.items():
            ttk.Label(explanation_frame, text=f"- {algo}: {explanation}", wraplength=410, justify=tk.LEFT).pack(
                anchor=tk.W, padx=6, pady=1
            )

    def _build_flat_tab(self):
        algo_frame = ttk.Frame(self.flat_tab)
        algo_frame.pack(fill=tk.X, pady=8, padx=4)

        ttk.Label(algo_frame, text="Flat Algorithm:").pack(side=tk.LEFT, padx=(0, 8))
        self.flat_algo_combobox = ttk.Combobox(
            algo_frame,
            textvariable=self.flat_algorithm,
            values=GraphSolver.AVAILABLE_ALGORITHMS,
            state="readonly",
            width=24,
        )
        self.flat_algo_combobox.pack(side=tk.LEFT)
        self.flat_algo_combobox.bind("<<ComboboxSelected>>", lambda _evt: self.on_flat_algo_change())

        self.flat_num_layers_frame = ttk.Frame(self.flat_tab)
        ttk.Label(self.flat_num_layers_frame, text="Flat Number of Layers:").pack(side=tk.LEFT, padx=(0, 8))
        self.flat_num_layers_entry = ttk.Entry(self.flat_num_layers_frame, textvariable=self.flat_num_layers, width=6)
        self.flat_num_layers_entry.pack(side=tk.LEFT)

        policy_frame = ttk.Frame(self.flat_tab)
        policy_frame.pack(fill=tk.X, pady=(0, 8), padx=4)

        ttk.Label(policy_frame, text="Touch Policy:").pack(side=tk.LEFT, padx=(0, 8))
        self.flat_policy_combobox = ttk.Combobox(
            policy_frame,
            textvariable=self.flat_touch_policy,
            values=["No edge/corner touching", "Allow corner touching"],
            state="readonly",
            width=24,
        )
        self.flat_policy_combobox.pack(side=tk.LEFT)

        priority_frame = ttk.Frame(self.flat_tab)
        priority_frame.pack(fill=tk.X, pady=(0, 8), padx=4)
        ttk.Label(priority_frame, text="Overlap Priority:").pack(side=tk.LEFT, padx=(0, 8))
        self.flat_priority_combobox = ttk.Combobox(
            priority_frame,
            textvariable=self.flat_priority_order,
            values=["Source order", "Largest first", "Smallest first"],
            state="readonly",
            width=24,
        )
        self.flat_priority_combobox.pack(side=tk.LEFT)

        info_frame = ttk.LabelFrame(self.flat_tab, text="Flat Complexity Behavior")
        info_frame.pack(fill=tk.X, padx=4, pady=(0, 6))

        ttk.Label(
            info_frame,
            text=(
                "No edge/corner touching: any contact forces different layers.\n"
                "Allow corner touching: point-only corner contacts may share layers.\n"
                "Overlap priority controls which shapes keep contested areas.\n"
                "Use force_k only when you intentionally accept less strict separation."
            ),
            wraplength=410,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=6, pady=6)

        self.on_flat_algo_change()

    def on_algo_change(self):
        if self.algorithm.get() == "force_k":
            self.num_layers_frame.pack(fill=tk.X, padx=4, pady=(0, 8))
        else:
            self.num_layers_frame.pack_forget()

    def on_flat_algo_change(self):
        if self.flat_algorithm.get() == "force_k":
            self.flat_num_layers_frame.pack(fill=tk.X, padx=4, pady=(0, 8))
        else:
            self.flat_num_layers_frame.pack_forget()

    def get_active_mode(self):
        tab_id = self.mode_notebook.select()
        tab_text = self.mode_notebook.tab(tab_id, "text")
        return "flat" if tab_text == "Flat Complexity" else "overlaid"

    def on_mode_change(self, _event=None):
        mode = self.get_active_mode()
        mode_result = self.results_by_mode.get(mode)

        self.results_text.delete(1.0, tk.END)
        if mode_result is None:
            self.results_text.insert(tk.END, f"Mode: {'Flat Complexity' if mode == 'flat' else 'Overlaid Complexity'}\n")
            self.save_button.config(state="disabled")
            self.save_single_button.config(state="disabled")
        else:
            self.results_text.insert(tk.END, mode_result["summary"])
            self.save_button.config(state="normal")
            self.save_single_button.config(state="normal")

    def select_file(self):
        filepath = filedialog.askopenfilename(
            title="Select SVG File",
            filetypes=(("SVG files", "*.svg"), ("All files", "*.*")),
        )
        if filepath:
            self.filepath = filepath
            self.filepath_label.config(text=os.path.basename(filepath))
            self.display_preview()
            self.results_by_mode["overlaid"] = None
            self.results_by_mode["flat"] = None
            self.on_mode_change()

    def display_preview(self):
        if not self.filepath:
            return

        try:
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1:
                self.root.after(100, self.display_preview)
                return

            png_data = svg2png(url=self.filepath, output_width=1200, output_height=1200)
            image = Image.open(io.BytesIO(png_data))

            img_width, img_height = image.size
            scale = min(canvas_width / img_width, canvas_height / img_height)
            new_width = max(1, int(img_width * scale))
            new_height = max(1, int(img_height * scale))

            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(resized_image)

            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(canvas_width // 2, canvas_height // 2, image=self.preview_image, anchor=tk.CENTER)
        except Exception as exc:
            print(f"Error displaying preview: {exc}")
            self.preview_canvas.delete("all")
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            self.preview_canvas.create_text(
                canvas_width // 2 if canvas_width > 1 else 200,
                canvas_height // 2 if canvas_height > 1 else 200,
                text="Preview not available",
                anchor=tk.CENTER,
            )

    def on_preview_resize(self, _event):
        if self.preview_image is not None:
            self.display_preview()

    def process_file(self):
        if not self.filepath:
            messagebox.showerror("Error", "Please select an SVG file first.")
            return

        mode = self.get_active_mode()

        self.process_button.config(state="disabled")
        self.save_button.config(state="disabled")
        self.save_single_button.config(state="disabled")
        self.progress["value"] = 0
        self.progress["maximum"] = 100
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, "Processing...\n")

        thread = threading.Thread(target=lambda: self.run_process_thread(mode), daemon=True)
        thread.start()
        self.animate_progress()

    def run_process_thread(self, mode):
        try:
            algorithm = self.algorithm.get()
            use_optimizer = self.use_optimizer.get()
            num_layers = self.num_layers.get() if algorithm == "force_k" else None

            flat_algorithm = self.flat_algorithm.get()
            flat_num_layers = self.flat_num_layers.get() if flat_algorithm == "force_k" else None
            flat_touch_policy = (
                "edge_or_overlap"
                if self.flat_touch_policy.get() == "Allow corner touching"
                else "any_touch"
            )
            flat_priority_order = {
                "Source order": "source",
                "Largest first": "largest_first",
                "Smallest first": "smallest_first",
            }.get(self.flat_priority_order.get(), "source")

            result = run_diastasis(
                self.filepath,
                algorithm=algorithm,
                use_optimizer=use_optimizer,
                num_layers=num_layers,
                mode=mode,
                flat_algorithm=flat_algorithm,
                flat_num_layers=flat_num_layers,
                flat_touch_policy=flat_touch_policy,
                flat_priority_order=flat_priority_order,
                clip_visible_boundaries=self.clip_visible_boundaries.get(),
            )

            if result and len(result) >= 5:
                shapes, coloring, summary, svg_width, svg_height = result
                self.results_by_mode[mode] = {
                    "shapes": shapes,
                    "coloring": coloring,
                    "summary": summary,
                    "svg_width": svg_width,
                    "svg_height": svg_height,
                }
                self.root.after(0, lambda: self.processing_complete(mode, summary))
            else:
                error_msg = result if isinstance(result, str) else "Processing failed with unknown error."
                self.root.after(0, lambda: self.processing_error(error_msg))

        except Exception as exc:
            traceback.print_exc()
            error_msg = f"Error during processing: {exc}"
            self.root.after(0, lambda: self.processing_error(error_msg))

    def animate_progress(self):
        if self.process_button["state"] == "disabled":
            current = self.progress["value"]
            if current < 90:
                self.progress["value"] = current + 2
            self.root.after(100, self.animate_progress)

    def processing_complete(self, mode, summary):
        self.progress["value"] = 100
        self.process_button.config(state="normal")

        current_mode = self.get_active_mode()
        if current_mode == mode:
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(tk.END, summary)
            self.save_button.config(state="normal")
            self.save_single_button.config(state="normal")
        else:
            self.save_button.config(state="disabled")
            self.save_single_button.config(state="disabled")

    def processing_error(self, error_msg):
        self.progress["value"] = 0
        self.process_button.config(state="normal")

        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, f"Error: {error_msg}")
        self.save_button.config(state="disabled")
        self.save_single_button.config(state="disabled")

        messagebox.showerror("Processing Error", error_msg)

    def save_layers(self):
        mode = self.get_active_mode()
        data = self.results_by_mode.get(mode)

        if not data:
            messagebox.showerror("Error", "No processed data for this mode. Please process first.")
            return

        original_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        default_filename = f"{original_filename}_{mode}_layered.svg"

        output_filepath = filedialog.asksaveasfilename(
            title="Save Layered SVG As...",
            defaultextension=".svg",
            filetypes=[("SVG files", "*.svg"), ("All files", "*.*")],
            initialfile=default_filename,
        )

        if not output_filepath:
            return

        try:
            output_dir = os.path.dirname(output_filepath)
            chosen_filename = os.path.basename(output_filepath)
            base_filename = os.path.splitext(chosen_filename)[0]

            save_layers_to_files(
                data["shapes"],
                data["coloring"],
                output_dir,
                base_filename,
                data["svg_width"],
                data["svg_height"],
                preserve_original_colors=self.clip_visible_boundaries.get(),
            )

            messagebox.showinfo("Success", f"Layered SVG saved successfully as:\n{output_filepath}")
        except Exception as exc:
            messagebox.showerror("Save Error", f"Error saving layers: {exc}")

    def save_single_layer(self):
        mode = self.get_active_mode()
        data = self.results_by_mode.get(mode)

        if not data:
            messagebox.showerror("Error", "No processed data for this mode. Please process first.")
            return

        original_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        default_filename = f"{original_filename}_{mode}_clipped_single.svg"

        output_filepath = filedialog.asksaveasfilename(
            title="Save Clipped 1-Layer SVG As...",
            defaultextension=".svg",
            filetypes=[("SVG files", "*.svg"), ("All files", "*.*")],
            initialfile=default_filename,
        )

        if not output_filepath:
            return

        try:
            save_single_layer_file(
                data["shapes"],
                output_filepath,
                data["svg_width"],
                data["svg_height"],
            )
            messagebox.showinfo("Success", f"Single-layer SVG saved successfully as:\n{output_filepath}")
        except Exception as exc:
            messagebox.showerror("Save Error", f"Error saving single-layer SVG: {exc}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DiastasisGUI(root)
    root.mainloop()
