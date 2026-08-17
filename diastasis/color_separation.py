"""
Color separation: grouping shapes into single-ink plates.

Covers the color-driven half of the pipeline — clustering shapes by fill,
recoloring them to their plate's representative ink, and consolidating
same-color fragments — as opposed to the overlap-driven graph coloring
in main.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .color_utils import color_distance, parse_color, rgb_to_hex
from .geometry_ops import safe_unary_union
from .svg_export import get_shape_fill
from .svg_parser import Shape

RGB = Tuple[int, int, int]


@dataclass
class _ColorCluster:
    """Running accumulator for one plate's ink color."""

    seed: RGB
    total: List[int] = field(default_factory=lambda: [0, 0, 0])
    count: int = 0

    def add(self, rgb: RGB) -> None:
        for channel in range(3):
            self.total[channel] += rgb[channel]
        self.count += 1

    def average(self) -> RGB:
        return (
            int(round(self.total[0] / self.count)),
            int(round(self.total[1] / self.count)),
            int(round(self.total[2] / self.count)),
        )


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
    clusters: List[_ColorCluster] = []
    coloring: Dict[int, int] = {}
    unresolved_ids: List[int] = []

    for idx, shape in enumerate(shapes):
        rgb = parse_color(get_shape_fill(shape, fallback_color=None))
        if rgb is None:
            unresolved_ids.append(idx)
            continue

        assigned = next(
            (cid for cid, cluster in enumerate(clusters) if color_distance(rgb, cluster.seed) <= tolerance),
            None,
        )
        if assigned is None:
            assigned = len(clusters)
            clusters.append(_ColorCluster(seed=rgb))

        clusters[assigned].add(rgb)
        coloring[idx] = assigned

    representatives: Dict[int, Optional[str]] = {}
    for cid, cluster in enumerate(clusters):
        representatives[cid] = rgb_to_hex(cluster.average())

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


def merge_same_color_fragments(
    shapes: List[Shape],
    grouped_coloring: Dict[int, List[int]],
) -> Tuple[List[Shape], Dict[int, List[int]], int]:
    """
    Within each layer, union shapes that share a resolved fill color into one
    consolidated geometry. Removes hairline seams between adjacent same-color
    fragments and yields one path per (layer, ink) — ideal for cut/print
    plates. Shapes of differing colors on a layer stay separate.

    Returns (new_shapes, new_grouped_coloring, original_shape_count).
    """
    original_count = len(shapes)
    new_shapes: List[Shape] = []
    new_grouped: Dict[int, List[int]] = defaultdict(list)

    for color_id in sorted(grouped_coloring):
        by_fill: Dict[object, List[int]] = defaultdict(list)
        for sid in grouped_coloring[color_id]:
            # Key on the resolved RGB so different notations for the same color
            # (#FF0000 vs #ff0000 vs red) merge; fall back to the raw string
            # for fills we cannot parse so they never collide under one key.
            raw_fill = get_shape_fill(shapes[sid], fallback_color=None)
            key: object = parse_color(raw_fill) or raw_fill
            by_fill[key].append(sid)

        for fill_ids in by_fill.values():
            geometries = [shapes[sid].geometry for sid in fill_ids if shapes[sid].geometry is not None]
            if not geometries:
                continue
            merged_geometry = geometries[0] if len(geometries) == 1 else safe_unary_union(geometries)
            if (
                merged_geometry is None
                or merged_geometry.is_empty
                or merged_geometry.geom_type not in ("Polygon", "MultiPolygon")
            ):
                continue

            new_id = len(new_shapes)
            new_shapes.append(
                Shape(
                    id=new_id,
                    geometry=merged_geometry,
                    metadata=dict(shapes[fill_ids[0]].metadata or {}),
                    # Geometry changed, so any original markup is no longer valid.
                    d_attribute=None,
                    native_shape=None,
                )
            )
            new_grouped[color_id].append(new_id)

    return new_shapes, new_grouped, original_count
