from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import networkx as nx
from rtree import index
from shapely.ops import unary_union
from shapely.validation import make_valid
from .color_utils import color_distance, parse_color, rgb_to_hex
from .graph_solver import GraphSolver
from .svg_parser import SVGParser, Shape
from .geometry_engine import GeometryEngine
# Export helpers live in svg_export; re-exported here for API compatibility.
from .svg_export import (  # noqa: F401
    build_layered_svg_string,
    generate_crop_marks_svg,
    get_shape_fill,
    polygon_to_svg_path_d,
    save_layers_to_files,
    save_layers_to_separate_files,
    save_single_layer_file,
)


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
    Return a proven lower bound for the required number of layers
    (largest clique in the conflict graph). Works for both modes.
    """
    return GraphSolver().clique_lower_bound(graph)


def flat_conflict_count(graph, coloring):
    """
    Count conflicting adjacency edges assigned to the same layer.
    """
    conflicts = 0
    for u, v in graph.edges():
        if coloring.get(u) == coloring.get(v):
            conflicts += 1
    return conflicts


def _sanitize_geometry(geometry):
    if geometry is None or geometry.is_empty:
        return geometry
    if geometry.is_valid:
        return geometry

    try:
        repaired = make_valid(geometry)
        if not repaired.is_empty:
            return repaired
    except Exception:
        pass

    try:
        repaired = geometry.buffer(0)
        if not repaired.is_empty:
            return repaired
    except Exception:
        pass

    return geometry


def _safe_difference(geom, mask):
    geom = _sanitize_geometry(geom)
    mask = _sanitize_geometry(mask)
    if geom is None or geom.is_empty:
        return geom
    if mask is None or mask.is_empty:
        return geom

    try:
        return geom.difference(mask)
    except Exception:
        try:
            return _sanitize_geometry(geom).difference(_sanitize_geometry(mask))
        except Exception:
            return geom


def _subtract_covered_area(geometry, placed_geometries, placed_index):
    """
    Subtract only the placed geometries whose bounds intersect the target.
    Equivalent to subtracting the union of all placed geometries, but keeps
    each difference local instead of against one giant accumulated union.
    """
    candidate_ids = list(placed_index.intersection(geometry.bounds))
    if not candidate_ids:
        return geometry
    try:
        mask = unary_union([placed_geometries[i] for i in candidate_ids])
    except Exception:
        mask = None
        for i in candidate_ids:
            candidate = placed_geometries[i]
            if mask is None:
                mask = candidate
                continue
            try:
                mask = mask.union(candidate)
            except Exception:
                try:
                    mask = _sanitize_geometry(mask).union(_sanitize_geometry(candidate))
                except Exception:
                    # Skip an un-unionable geometry rather than crash the run.
                    continue
    return _safe_difference(geometry, mask)


def clip_shapes_to_visible_boundaries(shapes):
    """
    Clip each shape to its visible area according to SVG paint order.
    Later elements are considered on top of earlier ones.
    """
    visible_by_index = {}
    occluder_geometries = []
    occluder_index = index.Index()

    # Traverse top-to-bottom (reverse source order).
    for idx in range(len(shapes) - 1, -1, -1):
        shape = shapes[idx]
        occluder = _sanitize_geometry(shape.geometry)
        if occluder is None or occluder.is_empty:
            continue
        geometry = _subtract_covered_area(occluder, occluder_geometries, occluder_index)

        if not geometry.is_empty:
            geometry = _sanitize_geometry(geometry)
            if not geometry.is_empty:
                visible_by_index[idx] = geometry

        if occluder is not None and not occluder.is_empty:
            occluder_index.insert(len(occluder_geometries), occluder.bounds)
            occluder_geometries.append(occluder)

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
    placed_geometries = []
    placed_index = index.Index()

    for shape in ordered_shapes:
        geometry = _sanitize_geometry(shape.geometry)
        if geometry is None or geometry.is_empty:
            continue

        geometry = _subtract_covered_area(geometry, placed_geometries, placed_index)
        if geometry.is_empty:
            continue

        geometry = _sanitize_geometry(geometry)
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

        placed_index.insert(len(placed_geometries), geometry.bounds)
        placed_geometries.append(geometry)

    return disjoint_shapes


def simplify_shapes_for_performance(
    shapes,
    svg_width,
    svg_height,
    tolerance_ratio=0.0005,
):
    """
    Reduce geometry complexity for very large files on weaker systems.
    Uses topology-preserving simplify with a tolerance relative to canvas size.
    """
    base_size = max(float(svg_width or 0), float(svg_height or 0), 1.0)
    tolerance = max(0.01, base_size * float(tolerance_ratio))

    simplified = []
    for shape in shapes:
        geometry = _sanitize_geometry(shape.geometry)
        if geometry is None or geometry.is_empty:
            continue
        try:
            geometry = geometry.simplify(tolerance, preserve_topology=True)
        except Exception:
            pass
        geometry = _sanitize_geometry(geometry)
        if geometry is None or geometry.is_empty:
            continue
        simplified.append(
            Shape(
                id=len(simplified),
                geometry=geometry,
                metadata=shape.metadata,
                d_attribute=None,
            )
        )

    return simplified, tolerance


def estimate_processing_complexity(svg_filepath):
    """
    Return a lightweight complexity estimate for UI/UX guidance.
    """
    parser = SVGParser()
    shapes, _, _ = parser.load_svg(svg_filepath)
    shape_count = len(shapes)
    if shape_count <= 1:
        return {
            "shape_count": shape_count,
            "candidate_pairs": 0,
            "all_pairs": 0,
            "density": 0.0,
            "complexity_label": "Low",
            "eta_seconds": 0.2,
        }

    geo_engine = GeometryEngine(use_spatial_index=True)
    candidate_pairs = geo_engine.count_candidate_pairs(shapes)

    all_pairs = (shape_count * (shape_count - 1)) // 2
    density = (candidate_pairs / all_pairs) if all_pairs else 0.0

    # Heuristic processing time model, tuned for interactive guidance only
    # (recalibrated for the vectorized engine and minimum_layers solver).
    eta_seconds = 0.15 + (shape_count * 0.0003) + (candidate_pairs * 0.00001)
    if shape_count > 2000:
        # The exact clique lower bound grows superlinearly on big graphs.
        eta_seconds *= 1.3

    if shape_count > 2000 or candidate_pairs > 400000:
        label = "Very High"
    elif shape_count > 1200 or candidate_pairs > 150000:
        label = "High"
    elif shape_count > 500 or candidate_pairs > 30000:
        label = "Medium"
    else:
        label = "Low"

    return {
        "shape_count": shape_count,
        "candidate_pairs": candidate_pairs,
        "all_pairs": all_pairs,
        "density": density,
        "complexity_label": label,
        "eta_seconds": eta_seconds,
    }


def build_flat_coloring(shapes, geo_engine, algorithm="minimum_layers", num_layers=None, touch_policy="any_touch"):
    """
    Build layers by coloring the touch/intersection graph.
    Adjacent (touching/intersecting) shapes are forced into different layers.
    """
    graph = build_flat_conflict_graph(shapes, geo_engine, touch_policy=touch_policy)
    return build_flat_coloring_from_graph(graph, algorithm=algorithm, num_layers=num_layers)


def build_flat_coloring_from_graph(graph, algorithm="minimum_layers", num_layers=None):
    solver = GraphSolver()
    return solver.solve_coloring(graph, algorithm=algorithm, use_optimizer=False, num_layers=num_layers)


def drop_sliver_fragments(shapes, canvas_area, min_area_ratio):
    """
    Drop fragments smaller than min_area_ratio of the canvas area.
    Returns (kept_shapes, dropped_count). Sub-visible slivers left over
    from flattening otherwise inflate conflicts and layer counts.
    """
    if min_area_ratio <= 0 or canvas_area <= 0:
        return shapes, 0

    threshold = canvas_area * min_area_ratio
    kept = []
    for shape in shapes:
        if shape.geometry is None or shape.geometry.area < threshold:
            continue
        kept.append(
            Shape(
                id=len(kept),
                geometry=shape.geometry,
                metadata=shape.metadata,
                d_attribute=shape.d_attribute,
                native_shape=shape.native_shape,
            )
        )
    return kept, len(shapes) - len(kept)


def separate_by_color(
    shapes: List[Shape], tolerance: float = 0.0
) -> Tuple[Dict[int, int], Dict[int, Optional[str]], int]:
    """
    Group shapes into plates by fill color. With tolerance > 0, colors within
    that RGB distance of an existing plate's seed color are merged into it
    (greedy first-fit clustering in source order). Shapes with no resolvable
    fill are collected into one trailing plate.

    Returns (coloring, representatives, unresolved_count) where:
      - coloring maps shape index -> plate id
      - representatives maps plate id -> average ink hex (None for the
        no-fill plate)
      - unresolved_count is the number of shapes with no parseable fill.
    """
    clusters = []  # each: {"seed": rgb, "sum": [r, g, b], "count": n}
    coloring = {}
    unresolved_ids = []

    for idx, shape in enumerate(shapes):
        rgb = parse_color(get_shape_fill(shape, fallback_color=None))
        if rgb is None:
            unresolved_ids.append(idx)
            continue

        assigned = next(
            (cid for cid, cluster in enumerate(clusters)
             if color_distance(rgb, cluster["seed"]) <= tolerance),
            None,
        )
        if assigned is None:
            assigned = len(clusters)
            clusters.append({"seed": rgb, "sum": [0, 0, 0], "count": 0})

        cluster = clusters[assigned]
        for channel in range(3):
            cluster["sum"][channel] += rgb[channel]
        cluster["count"] += 1
        coloring[idx] = assigned

    representatives: Dict[int, Optional[str]] = {}
    for cid, cluster in enumerate(clusters):
        n = cluster["count"]
        avg = (
            int(round(cluster["sum"][0] / n)),
            int(round(cluster["sum"][1] / n)),
            int(round(cluster["sum"][2] / n)),
        )
        representatives[cid] = rgb_to_hex(avg)

    if unresolved_ids:
        unresolved_plate = len(clusters)
        for idx in unresolved_ids:
            coloring[idx] = unresolved_plate
        representatives[unresolved_plate] = None

    return coloring, representatives, len(unresolved_ids)


def apply_plate_colors(
    shapes: List[Shape],
    coloring: Dict[int, int],
    representatives: Dict[int, Optional[str]],
) -> List[Shape]:
    """
    Return copies of shapes whose fill is set to their plate's representative
    ink, producing true single-ink plates. Shapes on the no-fill plate keep
    their original (fill-less) metadata.
    """
    recolored = []
    for idx, shape in enumerate(shapes):
        plate_id = coloring.get(idx)
        representative = representatives.get(plate_id) if plate_id is not None else None
        metadata = dict(shape.metadata or {})
        if representative is not None:
            # metadata['fill'] takes precedence over style in get_shape_fill.
            metadata["fill"] = representative
        recolored.append(
            Shape(
                id=idx,
                geometry=shape.geometry,
                metadata=metadata,
                d_attribute=shape.d_attribute,
                native_shape=shape.native_shape,
            )
        )
    return recolored


def _layer_breakdown_summary(
    shapes: List[Shape],
    coloring: Dict[int, int],
    canvas_area: float,
    row_label: str = "Color",
) -> str:
    """Tiny-fragment count and per-layer area share, shared by all modes."""
    layer_counts: Dict[int, int] = defaultdict(int)
    for color_id in coloring.values():
        layer_counts[color_id] += 1

    total_area = sum((shape.geometry.area if shape.geometry else 0.0) for shape in shapes)
    tiny_threshold = canvas_area * 0.0002 if canvas_area > 0 else 0.01
    tiny_count = sum(
        1 for shape in shapes
        if shape.geometry is not None and shape.geometry.area < tiny_threshold
    )

    text = f"Tiny fragments (<{tiny_threshold:.3f} area): {tiny_count}\n"
    text += "Layer area share:\n"
    for color_id in sorted(layer_counts):
        text += f"{row_label} {color_id}: {layer_counts[color_id]} shapes\n"
        if total_area > 0:
            layer_area = sum(
                shapes[sid].geometry.area
                for sid in coloring
                if coloring[sid] == color_id and shapes[sid].geometry is not None
            )
            text += f"  Area share: {(layer_area / total_area) * 100:.1f}%\n"
    return text


def run_diastasis(
    svg_filepath,
    algorithm="minimum_layers",
    use_optimizer=False,
    num_layers=None,
    mode="overlaid",
    flat_algorithm="minimum_layers",
    flat_num_layers=None,
    flat_touch_policy="any_touch",
    flat_priority_order="source",
    clip_visible_boundaries=False,
    performance_mode=False,
    performance_shape_threshold=1200,
    include_strokes=False,
    min_fragment_ratio=0.0,
    color_tolerance=0.0,
    unify_plate_colors=False,
):
    parser = SVGParser(include_strokes=include_strokes)
    shapes, svg_width, svg_height = parser.load_svg(svg_filepath)

    if not shapes:
        return None, None, "No shapes found in SVG."

    original_shape_count = len(shapes)
    used_performance_mode = False
    performance_tolerance = 0.0
    if performance_mode and original_shape_count >= performance_shape_threshold:
        shapes, performance_tolerance = simplify_shapes_for_performance(
            shapes,
            svg_width,
            svg_height,
        )
        used_performance_mode = True
        if not shapes:
            return None, None, "No shapes remain after performance simplification."

    if clip_visible_boundaries:
        shapes = clip_shapes_to_visible_boundaries(shapes)
        if not shapes:
            return None, None, "No visible shapes remain after visibility clipping."

    geo_engine = GeometryEngine(use_spatial_index=True)
    canvas_area = float(svg_width or 0) * float(svg_height or 0)

    if mode == "color":
        coloring, representatives, unresolved_count = separate_by_color(
            shapes, tolerance=color_tolerance
        )
        if unify_plate_colors:
            shapes = apply_plate_colors(shapes, coloring, representatives)

        num_plates = len(set(coloring.values()))
        summary = f"Processing complete (Color Separation). {num_plates} color plates.\n"
        summary += f"Visible boundary clipping: {'Enabled' if clip_visible_boundaries else 'Disabled'}\n"
        summary += f"Performance mode: {'Enabled' if performance_mode else 'Disabled'}\n"
        if include_strokes:
            summary += "Stroke-aware footprints: Enabled\n"
        if used_performance_mode:
            summary += (
                f"Performance simplification applied: {original_shape_count} -> {len(shapes)} shapes "
                f"(tolerance: {performance_tolerance:.3f})\n"
            )
        if color_tolerance > 0:
            summary += f"Color merge tolerance: {color_tolerance:.1f} (RGB distance)\n"
        if unify_plate_colors:
            summary += "Plate colors unified to representative ink.\n"
        if unresolved_count:
            summary += f"Shapes with no resolvable fill: {unresolved_count} (grouped as one plate)\n"

        summary += "\nPlate inks:\n"
        plate_counts = defaultdict(int)
        for plate_id in coloring.values():
            plate_counts[plate_id] += 1
        for plate_id in sorted(representatives):
            ink = representatives[plate_id] if representatives[plate_id] is not None else "(no fill)"
            summary += f"  Plate {plate_id}: {ink} — {plate_counts[plate_id]} shapes\n"
        summary += "\n"
        summary += _layer_breakdown_summary(shapes, coloring, canvas_area, row_label="Plate")

        grouped_coloring = defaultdict(list)
        for shape_id, plate_id in coloring.items():
            grouped_coloring[plate_id].append(shape_id)
        return shapes, grouped_coloring, summary, svg_width, svg_height

    if mode == "flat":
        # Enforce area exclusivity across all output layers.
        if not clip_visible_boundaries:
            shapes = make_shapes_area_disjoint(shapes, priority_order=flat_priority_order)
            if not shapes:
                return None, None, "No visible shapes remain after flat exclusivity flattening."

        shapes, dropped_slivers = drop_sliver_fragments(shapes, canvas_area, min_fragment_ratio)
        if not shapes:
            return None, None, "No shapes remain after sliver cleanup."

        graph = build_flat_conflict_graph(shapes, geo_engine, touch_policy=flat_touch_policy)

        coloring = build_flat_coloring_from_graph(
            graph,
            algorithm=flat_algorithm,
            num_layers=flat_num_layers,
        )
    else:
        # For weaker systems, skip overlap area calculations unless force_k needs them.
        if used_performance_mode and algorithm != "force_k":
            overlap_pairs = geo_engine.detect_overlap_pairs(shapes)
            overlaps = [(i, j, 1.0) for i, j in overlap_pairs]
        else:
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

        background_separated = False
        if largest_shape_id in coloring:
            background_color = coloring[largest_shape_id]
            shares_layer = any(
                shape_id != largest_shape_id and color == background_color
                for shape_id, color in coloring.items()
            )
            if shares_layer:
                # The background needs its own layer. Re-coloring the rest of
                # the graph with the background pinned out is never worse than
                # bumping only the background, and often saves a layer.
                bumped = {**coloring, largest_shape_id: max(coloring.values()) + 1}
                candidate = bumped
                if algorithm != "force_k":
                    rest_graph = graph.subgraph(
                        node for node in graph.nodes() if node != largest_shape_id
                    )
                    rest_coloring = solver.solve_coloring(
                        rest_graph, algorithm=algorithm, use_optimizer=use_optimizer
                    )
                    if rest_coloring:
                        recolored = {
                            **rest_coloring,
                            largest_shape_id: max(rest_coloring.values()) + 1,
                        }
                        if len(set(recolored.values())) < len(set(bumped.values())):
                            candidate = recolored
                coloring = candidate
                background_separated = True
        # --- End of largest shape separation ---

    num_colors = len(set(coloring.values()))
    mode_label = "Flat Complexity" if mode == "flat" else "Overlaid Complexity"
    summary = f"Processing complete ({mode_label}). Used {num_colors} layers.\n"
    summary += f"Visible boundary clipping: {'Enabled' if clip_visible_boundaries else 'Disabled'}\n"
    summary += f"Performance mode: {'Enabled' if performance_mode else 'Disabled'}\n"
    if include_strokes:
        summary += "Stroke-aware footprints: Enabled\n"
    if used_performance_mode:
        summary += (
            f"Performance simplification applied: {original_shape_count} -> {len(shapes)} shapes "
            f"(tolerance: {performance_tolerance:.3f})\n"
        )
    if mode == "flat":
        policy_label = "No edge/corner touching" if flat_touch_policy == "any_touch" else "Corners allowed"
        summary += f"Flat policy: {policy_label}\nFlat algorithm: {flat_algorithm}\n"
        priority_label = {
            "source": "Source order",
            "largest_first": "Largest first",
            "smallest_first": "Smallest first",
        }.get(flat_priority_order, "Source order")
        summary += f"Flat overlap priority: {priority_label}\n"
        if min_fragment_ratio > 0:
            summary += f"Sliver fragments dropped: {dropped_slivers} (< {min_fragment_ratio:.4%} of canvas)\n"
        lower_bound = flat_layer_lower_bound(graph)
        summary += f"Flat minimum proven required layers: {lower_bound}\n"
        if num_colors == lower_bound:
            summary += "Layer count is provably optimal.\n"
        if flat_algorithm == "force_k" and flat_num_layers is not None:
            conflicts = flat_conflict_count(graph, coloring)
            summary += (
                f"Flat force_k target: {flat_num_layers}\n"
                f"Flat conflict pairs introduced: {conflicts}\n"
            )
    else:
        lower_bound = flat_layer_lower_bound(graph)
        if background_separated:
            # A dedicated background layer needs chi(rest) + 1 layers, so the
            # sound bound is max(clique(G), clique(G without background) + 1).
            rest_graph = graph.subgraph(
                node for node in graph.nodes() if node != largest_shape_id
            )
            constrained_bound = max(lower_bound, flat_layer_lower_bound(rest_graph) + 1)
            summary += f"Minimum proven required layers (dedicated background): {constrained_bound}\n"
            if num_colors == lower_bound:
                summary += "Layer count is provably optimal.\n"
            elif num_colors == constrained_bound:
                summary += "Layer count is provably optimal given a dedicated background layer.\n"
        else:
            summary += f"Minimum proven required layers: {lower_bound}\n"
            if num_colors == lower_bound:
                summary += "Layer count is provably optimal.\n"
    summary += "\n"
    color_counts = defaultdict(int)
    for color_id in coloring.values():
        color_counts[color_id] += 1

    total_area = sum((shape.geometry.area if shape.geometry else 0.0) for shape in shapes)
    tiny_threshold = canvas_area * 0.0002 if canvas_area > 0 else 0.01
    tiny_count = sum(
        1 for shape in shapes
        if shape.geometry is not None and shape.geometry.area < tiny_threshold
    )

    if mode == "flat":
        overlap_metric = graph.number_of_edges()
        summary += f"Flat conflict graph edges: {overlap_metric}\n"
    else:
        overlap_metric = len(overlaps)
        summary += f"Overlaid overlap pairs detected: {overlap_metric}\n"

    summary += f"Tiny fragments (<{tiny_threshold:.3f} area): {tiny_count}\n"
    summary += "Layer area share:\n"

    for color_id in sorted(color_counts.keys()):
        count = color_counts[color_id]
        summary += f"Color {color_id}: {count} shapes\n"
        if total_area > 0:
            layer_area = sum(
                shapes[sid].geometry.area
                for sid in coloring.keys()
                if coloring[sid] == color_id and shapes[sid].geometry is not None
            )
            summary += f"  Area share: {(layer_area / total_area) * 100:.1f}%\n"

    # Invert coloring to group shapes by color_id for saving
    grouped_coloring = defaultdict(list)
    for shape_id, color_id in coloring.items():
        grouped_coloring[color_id].append(shape_id)

    return shapes, grouped_coloring, summary, svg_width, svg_height # Updated return values



