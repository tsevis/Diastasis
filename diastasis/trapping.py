"""
Trapping: keep bare paper from showing between inks when plates misregister.

Where two inks only touch, a press that is off by a hair leaves a white gap
between them. The standard remedy is to spread the lighter ink a little way
under the darker one: the darker ink keeps its edge (so the visible outline
does not move) and the lighter ink is already there when the plates slip.

The spread is clipped to the darker ink's own footprint, so it can never
reach bare paper or change a plate's outer silhouette.
"""

from typing import Dict, List, Optional

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from .color_utils import parse_color
from .geometry_ops import safe_difference, safe_unary_union, sanitize_geometry
from .svg_parser import Shape

TRAP_ORDERS = ("luminance", "plate")

# Arc segments per quarter circle when rounding the spread's outer corners.
_ARC_SEGMENTS = 8


def ink_lightness(hex_color: str) -> Optional[float]:
    """Perceived lightness of an ink (Rec. 709 weights on sRGB values), 0-255."""
    rgb = parse_color(hex_color)
    if rgb is None:
        return None
    red, green, blue = rgb
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def print_ranks(representatives: Dict[int, Optional[str]], order: str) -> Dict[int, int]:
    """
    Map plate id -> print position (0 prints first, underneath). Plates whose
    ink is unknown cannot be ranked and are left out, so they neither spread
    nor are spread into.

    order "luminance": lightest ink first (ties by plate id).
    order "plate":     plate id order, for presses run in a chosen sequence.
    """
    if order not in TRAP_ORDERS:
        raise ValueError(f"Unknown trap order {order!r}; expected one of {TRAP_ORDERS}.")

    lightness: Dict[int, float] = {}
    for plate_id, ink in representatives.items():
        value = ink_lightness(ink) if ink is not None else None
        if value is not None:
            lightness[plate_id] = value

    if order == "luminance":
        ranked = sorted(lightness, key=lambda pid: (-lightness[pid], pid))
    else:
        ranked = sorted(lightness)
    return {plate_id: position for position, plate_id in enumerate(ranked)}


def _polygonal_part(geometry: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
    """Drop the lines/points a boolean op leaves where shapes merely touch."""
    if geometry is None or geometry.is_empty:
        return None
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    if isinstance(geometry, GeometryCollection):
        polygons: List[Polygon] = []
        for part in geometry.geoms:
            if isinstance(part, Polygon):
                polygons.append(part)
            elif isinstance(part, MultiPolygon):
                polygons.extend(part.geoms)
        if polygons:
            return MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]
    return None


def _spread_under(
    shape: Shape,
    zone: BaseGeometry,
    on_top_geometries: List[BaseGeometry],
) -> Optional[BaseGeometry]:
    """The part of the on-top footprint inside `zone` (shape grown by the trap width), outside the shape."""
    covered = safe_unary_union(on_top_geometries)
    if covered is None:
        return None
    valid_zone = sanitize_geometry(zone)
    valid_covered = sanitize_geometry(covered)
    if valid_zone is None or valid_covered is None:
        return None
    reach = _polygonal_part(valid_zone.intersection(valid_covered))
    if reach is None:
        return None
    return _polygonal_part(safe_difference(reach, shape.geometry))


def trap_plates(
    shapes: List[Shape],
    grouped_coloring: Dict[int, List[int]],
    representatives: Dict[int, Optional[str]],
    width: float,
    order: str = "luminance",
) -> List[Shape]:
    """
    Return shapes with each one spread `width` units under every neighbour on
    a plate that prints after it. Shapes that gain nothing are returned as the
    same objects; spread shapes are new Shapes (their original path markup is
    dropped because the geometry no longer matches it). Input is not mutated.

    `width` is in SVG user units. Shapes on the same plate never trap each
    other, and plates with no known ink are skipped.
    """
    if width < 0:
        raise ValueError("Trap width must not be negative.")
    ranks = print_ranks(representatives, order)  # validates `order` even when width is 0
    if width == 0:
        return list(shapes)

    plate_of = {sid: pid for pid, sids in grouped_coloring.items() for sid in sids}
    candidates = [
        sid
        for sid, pid in plate_of.items()
        if pid in ranks and shapes[sid].geometry is not None and not shapes[sid].geometry.is_empty
    ]
    if not candidates:
        return list(shapes)

    geometries = [shapes[sid].geometry for sid in candidates]
    tree = STRtree(geometries)

    result = list(shapes)
    for sid in candidates:
        shape = shapes[sid]
        my_rank = ranks[plate_of[sid]]
        zone = shape.geometry.buffer(width, quad_segs=_ARC_SEGMENTS)
        on_top = [geometries[i] for i in tree.query(zone) if ranks[plate_of[candidates[i]]] > my_rank]
        if not on_top:
            continue

        extra = _spread_under(shape, zone, on_top)
        if extra is None:
            continue

        result[sid] = Shape(
            id=shape.id,
            geometry=sanitize_geometry(shape.geometry.union(extra)),
            metadata=dict(shape.metadata or {}),
            d_attribute=None,
            native_shape=None,
        )
    return result
