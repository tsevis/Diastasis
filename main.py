import os
from collections import defaultdict
import networkx as nx
from networkx.algorithms.approximation import clique
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
from graph_solver import GraphSolver
from svg_parser import SVGParser, Shape
from geometry_engine import GeometryEngine
import random

# Helper function to convert Shapely Polygon to SVG path 'd' attribute
def polygon_to_svg_path_d(polygon):
    if not polygon:
        return ""

    polygons = []
    if isinstance(polygon, Polygon):
        polygons = [polygon]
    elif isinstance(polygon, MultiPolygon):
        polygons = list(polygon.geoms)
    elif isinstance(polygon, GeometryCollection):
        polygons = [geom for geom in polygon.geoms if isinstance(geom, Polygon)]
    else:
        return ""

    path_data = []

    for poly in polygons:
        if poly.is_empty:
            continue

        # Exterior ring
        exterior_coords = poly.exterior.coords
        if exterior_coords:
            path_data.append(f"M {exterior_coords[0][0]} {exterior_coords[0][1]}")
            for x, y in exterior_coords[1:]:
                path_data.append(f"L {x} {y}")
            path_data.append("Z")

        # Interior rings (holes)
        for interior_ring in poly.interiors:
            interior_coords = interior_ring.coords
            if interior_coords:
                path_data.append(f"M {interior_coords[0][0]} {interior_coords[0][1]}")
                for x, y in interior_coords[1:]:
                    path_data.append(f"L {x} {y}")
                path_data.append("Z")

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


def build_flat_conflict_graph(shapes, geo_engine, touch_policy="any_touch"):
    """
    Build the flat-mode conflict graph where edges mean "cannot share layer".
    """
    graph = nx.Graph()
    graph.add_nodes_from((i, {"size": shape.geometry.area}) for i, shape in enumerate(shapes))

    for i, j in geo_engine.detect_contacts(shapes, touch_policy=touch_policy):
        # Unweighted adjacency is enough for flat separation.
        graph.add_edge(i, j, weight=1.0)

    return graph


def flat_layer_lower_bound(graph):
    """
    Return a proven lower bound for required layers in flat separation.
    """
    if graph.number_of_nodes() == 0:
        return 0
    # Maximum clique size is a strict lower bound for chromatic number.
    # Approximation gives a safe (possibly not tight) bound.
    return len(clique.max_clique(graph))


def flat_conflict_count(graph, coloring):
    """
    Count conflicting adjacency edges assigned to the same layer.
    """
    conflicts = 0
    for u, v in graph.edges():
        if coloring.get(u) == coloring.get(v):
            conflicts += 1
    return conflicts


def clip_shapes_to_visible_boundaries(shapes):
    """
    Clip each shape to its visible area according to SVG paint order.
    Later elements are considered on top of earlier ones.
    """
    visible_by_index = {}
    occluders = None

    # Traverse top-to-bottom (reverse source order).
    for idx in range(len(shapes) - 1, -1, -1):
        shape = shapes[idx]
        geometry = shape.geometry
        if occluders is not None and not occluders.is_empty:
            geometry = geometry.difference(occluders)

        if not geometry.is_empty:
            if not geometry.is_valid:
                geometry = geometry.buffer(0)
            if not geometry.is_empty:
                visible_by_index[idx] = geometry

        occluders = shape.geometry if occluders is None else occluders.union(shape.geometry)

    clipped_shapes = []
    for idx, shape in enumerate(shapes):
        geometry = visible_by_index.get(idx)
        if geometry is None or geometry.is_empty:
            continue
        clipped_shapes.append(
            Shape(
                id=len(clipped_shapes),
                geometry=geometry,
                metadata=shape.metadata,
                d_attribute=None,
            )
        )
    return clipped_shapes


def make_shapes_area_disjoint(shapes, priority_order="source"):
    """
    Flatten shapes so each area is owned by one shape only.
    For "source", follow SVG stacking (top-most elements first).
    """
    indexed_shapes = list(enumerate(shapes))
    if priority_order == "largest_first":
        ordered_shapes = [
            shape for _, shape in sorted(
                indexed_shapes,
                key=lambda item: ((item[1].geometry.area if item[1].geometry else 0), item[0]),
                reverse=True,
            )
        ]
    elif priority_order == "smallest_first":
        ordered_shapes = [
            shape for _, shape in sorted(
                indexed_shapes,
                key=lambda item: ((item[1].geometry.area if item[1].geometry else 0), -item[0]),
            )
        ]
    else:
        # SVG paints later elements on top, so process in reverse source order.
        ordered_shapes = [shape for _, shape in reversed(indexed_shapes)]

    disjoint_shapes = []
    occupied = None

    for shape in ordered_shapes:
        geometry = shape.geometry
        if occupied is not None and not occupied.is_empty:
            geometry = geometry.difference(occupied)

        if geometry.is_empty:
            continue

        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if geometry.is_empty:
            continue

        disjoint_shapes.append(
            Shape(
                id=len(disjoint_shapes),
                geometry=geometry,
                metadata=shape.metadata,
                # Geometry has changed, so original path data is no longer valid.
                d_attribute=None,
            )
        )

        occupied = geometry if occupied is None else occupied.union(geometry)

    return disjoint_shapes


def build_flat_coloring(shapes, geo_engine, algorithm="DSATUR", num_layers=None, touch_policy="any_touch"):
    """
    Build layers by coloring the touch/intersection graph.
    Adjacent (touching/intersecting) shapes are forced into different layers.
    """
    graph = build_flat_conflict_graph(shapes, geo_engine, touch_policy=touch_policy)

    solver = GraphSolver()
    return solver.solve_coloring(graph, algorithm=algorithm, use_optimizer=False, num_layers=num_layers)


def run_diastasis(
    svg_filepath,
    algorithm="DSATUR",
    use_optimizer=False,
    num_layers=None,
    mode="overlaid",
    flat_algorithm="DSATUR",
    flat_num_layers=None,
    flat_touch_policy="any_touch",
    flat_priority_order="source",
    clip_visible_boundaries=False,
):
    parser = SVGParser()
    shapes, svg_width, svg_height = parser.load_svg(svg_filepath)

    if not shapes:
        return None, None, "No shapes found in SVG."

    if clip_visible_boundaries:
        shapes = clip_shapes_to_visible_boundaries(shapes)
        if not shapes:
            return None, None, "No visible shapes remain after visibility clipping."

    geo_engine = GeometryEngine(use_spatial_index=True)

    if mode == "flat":
        # Enforce area exclusivity across all output layers.
        if not clip_visible_boundaries:
            shapes = make_shapes_area_disjoint(shapes, priority_order=flat_priority_order)
            if not shapes:
                return None, None, "No visible shapes remain after flat exclusivity flattening."

        graph = build_flat_conflict_graph(shapes, geo_engine, touch_policy=flat_touch_policy)

        coloring = build_flat_coloring(
            shapes,
            geo_engine,
            algorithm=flat_algorithm,
            num_layers=flat_num_layers,
            touch_policy=flat_touch_policy,
        )
    else:
        # Use the GeometryEngine to detect overlaps and get their areas
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
    mode_label = "Flat Complexity" if mode == "flat" else "Overlaid Complexity"
    summary = f"Processing complete ({mode_label}). Used {num_colors} layers.\n"
    summary += f"Visible boundary clipping: {'Enabled' if clip_visible_boundaries else 'Disabled'}\n"
    if mode == "flat":
        policy_label = "No edge/corner touching" if flat_touch_policy == "any_touch" else "Corners allowed"
        summary += f"Flat policy: {policy_label}\nFlat algorithm: {flat_algorithm}\n"
        priority_label = {
            "source": "Source order",
            "largest_first": "Largest first",
            "smallest_first": "Smallest first",
        }.get(flat_priority_order, "Source order")
        summary += f"Flat overlap priority: {priority_label}\n"
        graph = build_flat_conflict_graph(shapes, geo_engine, touch_policy=flat_touch_policy)
        lower_bound = flat_layer_lower_bound(graph)
        summary += f"Flat minimum proven required layers: {lower_bound}\n"
        if flat_algorithm == "force_k" and flat_num_layers is not None:
            conflicts = flat_conflict_count(graph, coloring)
            summary += (
                f"Flat force_k target: {flat_num_layers}\n"
                f"Flat conflict pairs introduced: {conflicts}\n"
            )
    summary += "\n"
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
                layered_svg_content += f'    <path d="{path_d}" fill="{fill_color}" stroke="none"/>' + '\n'
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


def save_single_layer_file(shapes, output_filepath, svg_width, svg_height):
    """
    Save all processed shapes into one single SVG layer.
    Useful for exporting clipped-visible results as one flat layer.
    """
    width = svg_width
    height = svg_height

    single_layer_svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">\n'
    )
    single_layer_svg += '  <g id="Single_Clipped_Layer">\n'

    for shape in shapes:
        path_d = shape.d_attribute if shape.d_attribute else polygon_to_svg_path_d(shape.geometry)
        if not path_d:
            continue

        style = shape.metadata.get("style") if shape.metadata else None
        if style:
            single_layer_svg += f'    <path d="{path_d}" style="{style}" stroke="none"/>\n'
        else:
            single_layer_svg += f'    <path d="{path_d}" fill="#000000" stroke="none"/>\n'

    single_layer_svg += "  </g>\n</svg>\n"

    with open(output_filepath, "w") as f:
        f.write(single_layer_svg)

    print(f"Single layer SVG saved to: {output_filepath}")
