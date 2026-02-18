import pytest
from shapely.geometry import box

from geometry_engine import GeometryEngine
from main import (
    build_flat_coloring,
    build_flat_conflict_graph,
    clip_shapes_to_visible_boundaries,
    flat_layer_lower_bound,
    get_shape_fill,
    make_shapes_area_disjoint,
    polygon_to_svg_path_d,
    run_diastasis,
    save_single_layer_file,
)
from svg_parser import Shape


def test_build_flat_coloring_separates_disjoint_components():
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(10, 0, 20, 10), metadata={}),  # Touching with shape 0
        Shape(id=2, geometry=box(100, 100, 110, 110), metadata={}),
        Shape(id=3, geometry=box(200, 200, 210, 210), metadata={}),
    ]

    coloring = build_flat_coloring(shapes, GeometryEngine(use_spatial_index=True))

    assert coloring[0] != coloring[1]
    assert set(coloring.keys()) == {0, 1, 2, 3}
    assert len(set(coloring.values())) >= 2


def test_build_flat_coloring_splits_touching_chain_into_multiple_layers():
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(10, 0, 20, 10), metadata={}),  # touches 0 and 2
        Shape(id=2, geometry=box(20, 0, 30, 10), metadata={}),
    ]

    coloring = build_flat_coloring(shapes, GeometryEngine(use_spatial_index=True))

    assert len(set(coloring.values())) >= 2
    assert coloring[0] != coloring[1]
    assert coloring[1] != coloring[2]


def test_build_flat_coloring_allows_corner_touch_when_policy_selected():
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(10, 10, 20, 20), metadata={}),  # corner touch only
    ]

    strict_coloring = build_flat_coloring(
        shapes,
        GeometryEngine(use_spatial_index=True),
        touch_policy="any_touch",
    )
    corner_allowed_coloring = build_flat_coloring(
        shapes,
        GeometryEngine(use_spatial_index=True),
        touch_policy="edge_or_overlap",
    )

    assert strict_coloring[0] != strict_coloring[1]
    assert corner_allowed_coloring[0] == corner_allowed_coloring[1]


def test_flat_layer_lower_bound_uses_clique_size():
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(5, 0, 15, 10), metadata={}),
        Shape(id=2, geometry=box(2, 5, 12, 15), metadata={}),
    ]
    graph = build_flat_conflict_graph(shapes, GeometryEngine(use_spatial_index=True))
    assert flat_layer_lower_bound(graph) >= 3


def test_run_diastasis_rejects_impossible_flat_force_k(tmp_path):
    svg_content = """
    <svg width="40" height="40" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="20" height="20" />
      <rect x="10" y="0" width="20" height="20" />
      <rect x="5" y="10" width="20" height="20" />
    </svg>
    """
    svg_file = tmp_path / "flat_guard.svg"
    svg_file.write_text(svg_content)

    result = run_diastasis(
        str(svg_file),
        mode="flat",
        flat_algorithm="force_k",
        flat_num_layers=2,
        flat_touch_policy="any_touch",
    )
    assert result is not None
    shapes, grouped_coloring, summary, _, _ = result
    assert len(shapes) > 0
    assert "Flat force_k target: 2" in summary


def test_make_shapes_area_disjoint_removes_pairwise_overlap():
    shapes = [
        Shape(id=0, geometry=box(0, 0, 20, 20), metadata={}),
        Shape(id=1, geometry=box(10, 0, 30, 20), metadata={}),
        Shape(id=2, geometry=box(5, 10, 25, 30), metadata={}),
    ]

    disjoint_shapes = make_shapes_area_disjoint(shapes)

    for i in range(len(disjoint_shapes)):
        for j in range(i + 1, len(disjoint_shapes)):
            assert disjoint_shapes[i].geometry.intersection(disjoint_shapes[j].geometry).area == 0


def test_make_shapes_area_disjoint_priority_largest_first_keeps_largest():
    small = Shape(id=0, geometry=box(0, 0, 10, 10), metadata={"name": "small"})
    large = Shape(id=1, geometry=box(0, 0, 20, 20), metadata={"name": "large"})

    disjoint_shapes = make_shapes_area_disjoint([small, large], priority_order="largest_first")

    # The largest should keep full area; smaller should be fully consumed.
    areas = sorted([s.geometry.area for s in disjoint_shapes], reverse=True)
    assert areas[0] == 400


def test_make_shapes_area_disjoint_priority_smallest_first_keeps_smallest():
    small = Shape(id=0, geometry=box(0, 0, 10, 10), metadata={"name": "small"})
    large = Shape(id=1, geometry=box(0, 0, 20, 20), metadata={"name": "large"})

    disjoint_shapes = make_shapes_area_disjoint([small, large], priority_order="smallest_first")

    # Smaller survives intact; larger loses the overlapping 10x10 area.
    areas = sorted([s.geometry.area for s in disjoint_shapes], reverse=True)
    assert areas[0] == 300
    assert areas[1] == 100


def test_make_shapes_area_disjoint_source_order_respects_svg_topmost_priority():
    bottom = Shape(id=0, geometry=box(0, 0, 20, 20), metadata={"name": "bottom"})
    top = Shape(id=1, geometry=box(0, 0, 10, 10), metadata={"name": "top"})

    disjoint_shapes = make_shapes_area_disjoint([bottom, top], priority_order="source")
    areas = sorted([s.geometry.area for s in disjoint_shapes], reverse=True)

    # Top keeps full 10x10, bottom loses that area from its 20x20.
    assert areas[0] == 300
    assert areas[1] == 100


def test_polygon_to_svg_path_d_supports_multipolygon():
    shape_a = box(0, 0, 10, 10)
    shape_b = box(20, 20, 30, 30)
    multi = shape_a.union(shape_b)

    path_d = polygon_to_svg_path_d(multi)
    assert path_d.count("M ") >= 2


def test_clip_shapes_to_visible_boundaries_removes_occluded_regions():
    bottom = Shape(id=0, geometry=box(0, 0, 20, 20), metadata={"name": "bottom"})
    top = Shape(id=1, geometry=box(0, 0, 10, 10), metadata={"name": "top"})

    clipped = clip_shapes_to_visible_boundaries([bottom, top])
    assert len(clipped) == 2
    areas = sorted([shape.geometry.area for shape in clipped], reverse=True)
    assert areas[0] == 300
    assert areas[1] == 100


def test_run_diastasis_with_visible_clipping_disables_overlap(tmp_path):
    svg_content = """
    <svg width="40" height="40" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="20" height="20" />
      <rect x="10" y="0" width="20" height="20" />
    </svg>
    """
    svg_file = tmp_path / "clip_test.svg"
    svg_file.write_text(svg_content)

    shapes, grouped_coloring, summary, _, _ = run_diastasis(
        str(svg_file),
        mode="overlaid",
        clip_visible_boundaries=True,
    )
    assert shapes is not None
    assert "Visible boundary clipping: Enabled" in summary
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            assert shapes[i].geometry.intersection(shapes[j].geometry).area == 0


def test_save_single_layer_file_writes_svg(tmp_path):
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={"style": "fill:#ff0000;"}),
        Shape(id=1, geometry=box(10, 0, 20, 10), metadata={"style": "fill:#00ff00;"}),
    ]
    output_path = tmp_path / "single_layer.svg"

    save_single_layer_file(shapes, str(output_path), 100, 100)

    assert output_path.exists()
    content = output_path.read_text()
    assert "<svg" in content
    assert 'id="Single_Clipped_Layer"' in content
    assert content.count("<path") >= 2


def test_get_shape_fill_prefers_metadata_fill_then_style():
    shape_with_fill = Shape(id=0, geometry=box(0, 0, 1, 1), metadata={"fill": "#112233", "style": "fill:#ff0000;"})
    assert get_shape_fill(shape_with_fill, fallback_color="#000000") == "#112233"

    shape_with_style = Shape(id=1, geometry=box(0, 0, 1, 1), metadata={"style": "stroke:#000; fill: rgb(10,20,30);"})
    assert get_shape_fill(shape_with_style, fallback_color="#000000") == "rgb(10,20,30)"

    shape_none = Shape(id=2, geometry=box(0, 0, 1, 1), metadata={"fill": "none", "style": "fill:none;"})
    assert get_shape_fill(shape_none, fallback_color="#000000") == "#000000"
