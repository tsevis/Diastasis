"""
SVG export: writes processed layers back out with the highest fidelity
available per shape — original path data, original native element markup,
or a generated path, in that order.
"""
import colorsys
import os
import re
from typing import Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import quoteattr

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

from .svg_parser import Shape


def _attr(value) -> str:
    """Quote and escape a value for safe use as an XML attribute."""
    return quoteattr(str(value))

BASE_COLOR_MAP = {
    0: "#FF0000", 1: "#00FF00", 2: "#0000FF", 3: "#FFFF00",
    4: "#FF00FF", 5: "#00FFFF", 6: "#FFA500", 7: "#800080",
    8: "#FFC0CB", 9: "#A52A2A", 10: "#808080", 11: "#000000",
}

# profile -> (path precision, include crop marks)
EXPORT_PROFILES = {
    "Illustrator-safe": (3, True),
    "Print": (4, True),
    "Web": (2, False),
}


def resolve_export_profile(export_profile: Optional[str]) -> Tuple[str, int, bool]:
    profile = export_profile if export_profile in EXPORT_PROFILES else "Illustrator-safe"
    path_precision, include_crop_marks = EXPORT_PROFILES[profile]
    return profile, path_precision, include_crop_marks


# Helper function to convert Shapely Polygon to SVG path 'd' attribute
def polygon_to_svg_path_d(polygon, precision: int = 3) -> str:
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
            path_data.append(f"M {exterior_coords[0][0]:.{precision}f} {exterior_coords[0][1]:.{precision}f}")
            for x, y in exterior_coords[1:]:
                path_data.append(f"L {x:.{precision}f} {y:.{precision}f}")
            path_data.append("Z")

        # Interior rings (holes)
        for interior_ring in poly.interiors:
            interior_coords = interior_ring.coords
            if interior_coords:
                path_data.append(f"M {interior_coords[0][0]:.{precision}f} {interior_coords[0][1]:.{precision}f}")
                for x, y in interior_coords[1:]:
                    path_data.append(f"L {x:.{precision}f} {y:.{precision}f}")
                path_data.append("Z")

    return " ".join(path_data)


# Helper function to generate SVG crop marks
def generate_crop_marks_svg(width: float, height: float, mark_length: float = 10) -> str:
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


def get_shape_fill(shape: Shape, fallback_color: str = "#CCCCCC") -> str:
    """
    Return original shape fill color from metadata/style when available.

    Parser-produced metadata already resolves style and inherited fills
    into metadata['fill']; the style fallback below serves Shape objects
    constructed directly by API users.
    """
    metadata = shape.metadata or {}

    fill_attr = metadata.get("fill")
    if fill_attr and str(fill_attr).strip().lower() not in ("none", "transparent"):
        return fill_attr

    style = metadata.get("style") or ""
    style_match = re.search(r"(?:^|;)\s*fill\s*:\s*([^;]+)", style, flags=re.IGNORECASE)
    if style_match:
        style_fill = style_match.group(1).strip()
        if style_fill.lower() not in ("none", "transparent"):
            return style_fill

    return fallback_color


def shape_element_markup(shape: Shape, fill: str, path_precision: int = 3) -> Optional[str]:
    """
    Render one shape as SVG markup with the best available fidelity:
    original path data, original native element, or a generated path.
    All values sourced from the input SVG are escaped before re-emission.
    """
    if shape.d_attribute:
        return f'<path d={_attr(shape.d_attribute)} fill={_attr(fill)} stroke="none"/>'

    native = getattr(shape, "native_shape", None)
    if native and native.get("attrs"):
        attrs = " ".join(f'{name}={_attr(value)}' for name, value in native["attrs"].items())
        return f'<{native["tag"]} {attrs} fill={_attr(fill)} stroke="none"/>'

    path_d = polygon_to_svg_path_d(shape.geometry, precision=path_precision)
    if not path_d:
        return None
    # Generated paths encode holes as extra subpaths; even-odd makes them render.
    return f'<path d="{path_d}" fill={_attr(fill)} fill-rule="evenodd" stroke="none"/>'


GOLDEN_RATIO_CONJUGATE = 0.618033988749895


def build_layer_color_map(color_ids: Iterable[int]) -> Dict[int, str]:
    """
    Deterministic colors: a fixed palette for the first twelve layers and a
    golden-angle hue walk beyond, so re-runs always produce the same files.
    """
    color_map = dict(BASE_COLOR_MAP)
    for color_id in color_ids:
        if color_id not in color_map:
            hue = (color_id * GOLDEN_RATIO_CONJUGATE) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
            color_map[color_id] = f'#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}'
    return color_map


def _svg_document(width, height, body: str, profile: str, extra_attrs: str = "") -> str:
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" data-export-profile="{profile}"{extra_attrs}>\n'
        f"{body}"
        "</svg>\n"
    )


def _layer_group_markup(
    shapes: List[Shape],
    shape_ids: List[int],
    layer_name: str,
    fill_color: str,
    path_precision: int,
    preserve_original_colors: bool,
) -> str:
    lines = [f'  <g id="{layer_name}">']
    for shape_id in shape_ids:
        shape = shapes[shape_id]
        fill = get_shape_fill(shape, fallback_color=fill_color) if preserve_original_colors else fill_color
        markup = shape_element_markup(shape, fill, path_precision)
        if markup:
            lines.append(f"    {markup}")
    lines.append("  </g>")
    return "\n".join(lines) + "\n"


def build_layered_svg_string(
    shapes: List[Shape],
    coloring: Dict[int, List[int]],
    svg_width: float,
    svg_height: float,
    preserve_original_colors: bool = False,
    export_profile: str = "Illustrator-safe",
) -> str:
    """Build the full layered SVG document, one <g> group per layer."""
    profile, path_precision, include_crop_marks = resolve_export_profile(export_profile)
    color_map = build_layer_color_map(coloring.keys())

    body = ""
    for color_id in sorted(coloring.keys()):
        body += _layer_group_markup(
            shapes,
            coloring[color_id],
            layer_name=f"Layer_Color_{color_id}",
            fill_color=color_map.get(color_id, "#CCCCCC"),
            path_precision=path_precision,
            preserve_original_colors=preserve_original_colors,
        )

    if include_crop_marks:
        body += f'  <g id="Crop_Marks">\n{generate_crop_marks_svg(svg_width, svg_height)}\n  </g>\n'

    return _svg_document(svg_width, svg_height, body, profile)


def save_layers_to_files(
    shapes: List[Shape],
    coloring: Dict[int, List[int]],
    output_dir: str,
    original_filename: str,
    svg_width: float,
    svg_height: float,
    preserve_original_colors: bool = False,
    export_profile: str = "Illustrator-safe",
) -> str:
    """Write all layers into one SVG, one <g> group per layer."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    content = build_layered_svg_string(
        shapes, coloring, svg_width, svg_height,
        preserve_original_colors=preserve_original_colors,
        export_profile=export_profile,
    )

    output_filepath = os.path.join(output_dir, f"{original_filename}_layered.svg")
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Layered SVG saved to: {output_filepath}")
    return output_filepath


def save_layers_to_separate_files(
    shapes: List[Shape],
    coloring: Dict[int, List[int]],
    output_dir: str,
    original_filename: str,
    svg_width: float,
    svg_height: float,
    preserve_original_colors: bool = False,
    export_profile: str = "Illustrator-safe",
) -> List[str]:
    """
    Write one SVG file per layer, all on the same canvas with the same crop
    marks so the files register perfectly when stacked in production.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    profile, path_precision, include_crop_marks = resolve_export_profile(export_profile)
    color_map = build_layer_color_map(coloring.keys())
    sorted_color_ids = sorted(coloring.keys())
    total = len(sorted_color_ids)

    written = []
    for position, color_id in enumerate(sorted_color_ids, start=1):
        body = _layer_group_markup(
            shapes,
            coloring[color_id],
            layer_name=f"Layer_Color_{color_id}",
            fill_color=color_map.get(color_id, "#CCCCCC"),
            path_precision=path_precision,
            preserve_original_colors=preserve_original_colors,
        )
        if include_crop_marks:
            body += f'  <g id="Crop_Marks">\n{generate_crop_marks_svg(svg_width, svg_height)}\n  </g>\n'

        filepath = os.path.join(output_dir, f"{original_filename}_layer_{position}of{total}.svg")
        extra = f' data-layer="{position}" data-layer-total="{total}"'
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_svg_document(svg_width, svg_height, body, profile, extra_attrs=extra))
        written.append(filepath)

    print(f"{total} layer files saved to: {output_dir}")
    return written


def save_single_layer_file(shapes: List[Shape], output_filepath: str, svg_width: float, svg_height: float) -> str:
    """
    Save all processed shapes into one single SVG layer.
    Useful for exporting clipped-visible results as one flat layer.
    """
    lines = [
        f'<svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" '
        'xmlns="http://www.w3.org/2000/svg">',
        '  <g id="Single_Clipped_Layer">',
    ]

    for shape in shapes:
        fill = get_shape_fill(shape, fallback_color="#000000")
        markup = shape_element_markup(shape, fill)
        if markup:
            lines.append(f"    {markup}")

    lines.extend(["  </g>", "</svg>", ""])

    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Single layer SVG saved to: {output_filepath}")
    return output_filepath
