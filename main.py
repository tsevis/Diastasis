import os
from collections import defaultdict
from graph_solver import GraphSolver
from svg_parser import SVGParser, Shape
from geometry_engine import GeometryEngine
import random

# Helper function to convert Shapely Polygon to SVG path 'd' attribute
def polygon_to_svg_path_d(polygon):
    if not polygon:
        return ""
    
    path_data = []
    
    # Exterior ring
    exterior_coords = polygon.exterior.coords
    if exterior_coords:
        path_data.append(f"M {exterior_coords[0][0]} {exterior_coords[0][1]}")
        for x, y in exterior_coords[1:]:
            path_data.append(f"L {x} {y}")
        path_data.append("Z") # Close the path

    # Interior rings (holes)
    for interior_ring in polygon.interiors:
        interior_coords = interior_ring.coords
        if interior_coords:
            path_data.append(f"M {interior_coords[0][0]} {interior_coords[0][1]}")
            for x, y in interior_coords[1:]:
                path_data.append(f"L {x} {y}")
            path_data.append("Z") # Close the hole path
            
    return " ".join(path_data)

# Helper function to generate SVG crop marks
def generate_crop_marks_svg(width, height, mark_length=10):
    marks_svg = []
    # Top-left corner
    marks_svg.append(f'<path d="M 0 {mark_length} L 0 0 L {mark_length} 0" stroke="black" stroke-width="0.5" fill="none"/>')
    # Top-right corner
    marks_svg.append(f'<path d="M {width - mark_length} 0 L {width} 0 L {width} {mark_length}" stroke="black" stroke-width="0.5" fill="none"/>')
    # Bottom-left corner
    marks_svg.append(f'<path d="M 0 {height - mark_length} L 0 {height} L {mark_length} {height}" stroke="black" stroke-width="0.5" fill="none"/>')
    # Bottom-right corner
    marks_svg.append(f'<path d="M {width - mark_length} {height} L {width} {height} L {width} {height - mark_length}" stroke="black" stroke-width="0.5" fill="none"/>')
    return "\n".join(marks_svg)


from geometry_engine import GeometryEngine


def run_diastasis(svg_filepath, algorithm="DSATUR", use_optimizer=False, num_layers=None):
    parser = SVGParser()
    shapes, svg_width, svg_height = parser.load_svg(svg_filepath)

    if not shapes:
        return None, None, "No shapes found in SVG."

    # Use the GeometryEngine to detect overlaps and get their areas
    geo_engine = GeometryEngine(use_spatial_index=True)
    overlaps = geo_engine.detect_overlaps(shapes)

    solver = GraphSolver()
    # Build the weighted networkx graph
    graph = solver.build_overlap_graph(shapes, overlaps)
    
    # Call solve_coloring with the new parameters
    coloring = solver.solve_coloring(graph, algorithm=algorithm, use_optimizer=use_optimizer, num_layers=num_layers)

    # --- Identify and separate the largest shape (background) ---
    largest_shape_id = -1
    max_area = -1
    for i, shape in enumerate(shapes):
        if shape.geometry and shape.geometry.area > max_area:
            max_area = shape.geometry.area
            largest_shape_id = i
    
    if largest_shape_id != -1:
        # Assign a new, distinct color ID to the largest shape
        # Find the current maximum color ID used
        max_existing_color_id = max(coloring.values()) if coloring else -1
        new_background_color_id = max_existing_color_id + 1
        coloring[largest_shape_id] = new_background_color_id
    # --- End of largest shape separation ---

    num_colors = len(set(coloring.values()))
    summary = f"Processing complete. Used {num_colors} colors.\n\n"
    for color_id in sorted(set(coloring.values())):
        count = list(coloring.values()).count(color_id)
        summary += f"Color {color_id}: {count} shapes\n"

    # Invert coloring to group shapes by color_id for saving
    grouped_coloring = defaultdict(list)
    for shape_id, color_id in coloring.items():
        grouped_coloring[color_id].append(shape_id)

    return shapes, grouped_coloring, summary, svg_width, svg_height # Updated return values



def save_layers_to_files(shapes, coloring, output_dir, original_filename, svg_width, svg_height): # Updated signature
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Use actual SVG dimensions for the SVG canvas
    width = svg_width # Updated line
    height = svg_height # Updated line

    # Define a simple color map. This should ideally be more robust or come from the coloring process.
    color_map = {
        0: "#FF0000", 1: "#00FF00", 2: "#0000FF", 3: "#FFFF00",
        4: "#FF00FF", 5: "#00FFFF", 6: "#FFA500", 7: "#800080",
        8: "#FFC0CB", 9: "#A52A2A", 10: "#808080", 11: "#000000"
    }
    # Extend color_map if more colors are needed
    for i in range(len(color_map), max(coloring.keys(), default=-1) + 1):
        color_map[i] = '#%06X' % random.randint(0, 0xFFFFFF)


    # Start building the single layered SVG content
    layered_svg_content = f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">' + '\n'

    # Sort color_ids to ensure consistent layer order
    sorted_color_ids = sorted(coloring.keys())

    for color_id in sorted_color_ids:
        color_shapes = coloring[color_id]
        layer_name = f"Layer_Color_{color_id}" # Illustrator will use this as layer name
        fill_color = color_map.get(color_id, "#CCCCCC") # Default to grey if color not in map

        layered_svg_content += f'  <g id="{layer_name}">' + '\n'
        for shape_id in color_shapes:
            shape = shapes[shape_id]
            path_d = ""
            if shape.d_attribute: # If original d_attribute exists (for path elements)
                path_d = shape.d_attribute
            else: # For other shapes (rect, circle, polygon) converted to Shapely Polygon
                path_d = polygon_to_svg_path_d(shape.geometry)
            
            if path_d: # Only add if path_d is not empty
                layered_svg_content += f'    <path d="{path_d}" fill="{fill_color}" stroke="black" stroke-width="1"/>' + '\n'
        layered_svg_content += '  </g>' + '\n'

    # Add crop marks layer
    crop_marks_svg = generate_crop_marks_svg(width, height)
    layered_svg_content += f'  <g id="Crop_Marks">' + '\n' + f'{crop_marks_svg}' + '\n' + '  </g>' + '\n' # Corrected line

    layered_svg_content += '</svg>' + '\n' # Add a final newline for good measure

    # Define the output filepath for the single layered SVG
    output_filepath = os.path.join(output_dir, f"{original_filename}_layered.svg")

    with open(output_filepath, 'w') as f:
        f.write(layered_svg_content)

    print(f"Layered SVG saved to: {output_filepath}")
