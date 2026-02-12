from typing import List, Dict
from svg_parser import Shape
import os
import random
from shapely.geometry import MultiPolygon

class OutputGenerator:
    def create_layer_files(self, shapes: List[Shape], coloring: Dict[int, int], output_dir: str, original_filename: str):
        """Creates SVG files for each layer."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        if not coloring:
            return

        num_layers = max(coloring.values()) + 1
        for layer_num in range(num_layers):
            layer_shapes = [shapes[i] for i, color in coloring.items() if color == layer_num]
            
            # Generate a random color for the layer
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)
            layer_color = f"fill:rgb({r},{g},{b});"

            svg_content = self.generate_svg_layer(layer_shapes, layer_num, shapes, layer_color, original_filename)
            filepath = os.path.join(output_dir, f"{original_filename}_layer_{layer_num + 1}.svg")
            with open(filepath, "w") as f:
                f.write(svg_content)

    def generate_svg_layer(self, layer_shapes: List[Shape], layer_num: int, all_shapes: List[Shape], layer_color: str, original_filename: str) -> str:
        """Generates the SVG content for a single layer."""
        svg_paths = []
        for shape in layer_shapes:
            path_str = self.to_svg_path(shape, layer_color)
            svg_paths.append(path_str)
            
        registration_marks = self.add_registration_marks(all_shapes, f"{original_filename}_layer_{layer_num + 1}")
        svg_paths.extend(registration_marks)
        
        # This is a simplified implementation. A more robust one would use a library
        # to construct the SVG XML.
        svg_header = '<svg xmlns="http://www.w3.org/2000/svg">'
        svg_footer = '</svg>'
        
        return f"{svg_header}\n" + "\n".join(svg_paths) + f"\n{svg_footer}"

    def to_svg_path(self, shape: Shape, color: str) -> str:
        """Converts a shape back to an SVG path string."""
        # This is highly simplified and needs a proper implementation
        # to handle different shapes and metadata.
        path_data = "M " + " L ".join([f"{x},{y}" for x, y in shape.geometry.exterior.coords]) + " Z"
        
        style = shape.metadata.get('style', '')
        # Replace the original fill color with the layer color
        style = f"{color} {style}"

        transform = shape.metadata.get('transform', '')
        # Include the original ID
        shape_id = shape.metadata.get('id', '')
        return f'<path d="{path_data}" style="{style}" transform="{transform}" id="{shape_id}" />'

    def add_registration_marks(self, shapes: List[Shape], layer_name: str) -> List[str]:
        """Adds registration marks to the SVG."""
        if not shapes:
            return []
            
        # Get the bounding box of all shapes
        all_geometries = [shape.geometry for shape in shapes]
        multi_polygon = MultiPolygon([geom for geom in all_geometries if geom.is_valid])
        bounds = multi_polygon.bounds
        min_x, min_y, max_x, max_y = bounds
        
        # Add a margin around the bounding box
        margin = 50
        min_x -= margin
        min_y -= margin
        max_x += margin
        max_y += margin

        # Create registration marks
        cross_size = 10
        
        # Top-left cross
        reg_mark1 = f'<line x1="{min_x - cross_size}" y1="{min_y}" x2="{min_x + cross_size}" y2="{min_y}" stroke="black" />'
        reg_mark2 = f'<line x1="{min_x}" y1="{min_y - cross_size}" x2="{min_x}" y2="{min_y + cross_size}" stroke="black" />'
        
        # Top-right cross
        reg_mark3 = f'<line x1="{max_x - cross_size}" y1="{min_y}" x2="{max_x + cross_size}" y2="{min_y}" stroke="black" />'
        reg_mark4 = f'<line x1="{max_x}" y1="{min_y - cross_size}" x2="{max_x}" y2="{min_y + cross_size}" stroke="black" />'

        # Bottom-left cross
        reg_mark5 = f'<line x1="{min_x - cross_size}" y1="{max_y}" x2="{min_x + cross_size}" y2="{max_y}" stroke="black" />'
        reg_mark6 = f'<line x1="{min_x}" y1="{max_y - cross_size}" x2="{min_x}" y2="{max_y + cross_size}" stroke="black" />'

        # Bottom-right cross
        reg_mark7 = f'<line x1="{max_x - cross_size}" y1="{max_y}" x2="{max_x + cross_size}" y2="{max_y}" stroke="black" />'
        reg_mark8 = f'<line x1="{max_x}" y1="{max_y - cross_size}" x2="{max_x}" y2="{max_y + cross_size}" stroke="black" />'
        
        # Add layer name
        layer_name_text = f'<text x="{min_x}" y="{min_y - cross_size - 5}" font-family="Arial" font-size="10" fill="black">{layer_name}</text>'

        return [reg_mark1, reg_mark2, reg_mark3, reg_mark4, reg_mark5, reg_mark6, reg_mark7, reg_mark8, layer_name_text]


    def preserve_original_styling(self, shape: Shape) -> str:
        """Preserves the original styling of the shape."""
        # This is a placeholder. The actual implementation will be in to_svg_path.
        return ""

    def create_summary_report(self, coloring: Dict[int, int], shapes: List[Shape], output_dir: str, original_filename: str, processing_time: float, memory_usage: float) -> str:
        """Creates a summary report of the processing."""
        if not coloring:
            return ""
            
        num_layers = max(coloring.values()) + 1
        report = f"Mozaix Diastasis - Shape Separation Report\n"
        report += "==========================================\n"
        report += f"Input file: {original_filename}.svg\n"
        report += f"Total shapes: {len(shapes)}\n"
        report += f"Number of layers created: {num_layers}\n"
        report += f"Processing time: {processing_time:.2f} seconds\n"
        report += f"Memory usage: {memory_usage:.2f} GB\n\n"
        report += "Layer distribution:\n"
        for layer_num in range(num_layers):
            num_shapes_in_layer = len([c for c in coloring.values() if c == layer_num])
            report += f"Layer {layer_num + 1}: {num_shapes_in_layer} shapes\n"

        return report