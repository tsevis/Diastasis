import pytest
import os
from svg_parser import SVGParser, Shape
from shapely.geometry import Polygon, Point, box

# Create a dummy SVG file for testing
@pytest.fixture
def dummy_svg_file(tmp_path):
    svg_content = """
    <svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
      <rect x="10" y="10" width="50" height="50" id="rect1" />
      <circle cx="100" cy="100" r="30" id="circle1" />
      <ellipse cx="150" cy="50" rx="40" ry="20" id="ellipse1" />
      <polygon points="10,150 60,180 30,190" id="polygon1" />
      <path d="M 10 10 L 20 20 L 30 10 Z" id="path1" />
    </svg>
    """
    file_path = tmp_path / "dummy.svg"
    file_path.write_text(svg_content)
    return str(file_path)

def test_load_svg(dummy_svg_file):
    parser = SVGParser()
    shapes, width, height = parser.load_svg(dummy_svg_file)
    assert len(shapes) == 5
    assert width == 200
    assert height == 200

def test_extract_shapes(dummy_svg_file):
    parser = SVGParser()
    # Load the SVG to get the root element
    from lxml import etree
    tree = etree.parse(dummy_svg_file)
    root = tree.getroot()
    shapes = parser.extract_shapes(root)
    assert len(shapes) == 5

    # Check types and basic properties
    for shape in shapes:
        assert isinstance(shape, Shape)
        assert isinstance(shape.geometry, Polygon)
        assert 'id' in shape.metadata

def test_convert_to_polygon_rect():
    parser = SVGParser()
    from lxml import etree
    element = etree.fromstring('<rect x="0" y="0" width="10" height="10" />')
    polygon = parser.convert_to_polygon(element)
    assert isinstance(polygon, Polygon)
    assert polygon.area == 100

def test_convert_to_polygon_circle():
    parser = SVGParser()
    from lxml import etree
    element = etree.fromstring('<circle cx="0" cy="0" r="10" />')
    polygon = parser.convert_to_polygon(element)
    assert isinstance(polygon, Polygon)
    # Check if it's a reasonable approximation of a circle
    assert polygon.area > 300 and polygon.area < 320 # pi * r^2 = 314.15

def test_convert_to_polygon_ellipse():
    parser = SVGParser()
    from lxml import etree
    element = etree.fromstring('<ellipse cx="0" cy="0" rx="10" ry="5" />')
    polygon = parser.convert_to_polygon(element)
    assert isinstance(polygon, Polygon)
    # Check if it's a reasonable approximation of an ellipse
    assert polygon.area > 150 and polygon.area < 160 # pi * rx * ry = 157.07

def test_convert_to_polygon_polygon():
    parser = SVGParser()
    from lxml import etree
    element = etree.fromstring('<polygon points="0,0 10,0 5,10" />')
    polygon = parser.convert_to_polygon(element)
    assert isinstance(polygon, Polygon)
    assert polygon.area == 50

def test_convert_to_polygon_path():
    parser = SVGParser()
    from lxml import etree
    element = etree.fromstring('<path d="M 0 0 L 10 0 L 5 10 Z" />')
    polygon = parser.convert_to_polygon(element)
    assert isinstance(polygon, Polygon)
    assert polygon.area == 50

def test_preserve_metadata():
    parser = SVGParser()
    from lxml import etree
    element = etree.fromstring('<rect id="test_id" style="fill:red;" transform="translate(10,10)" fill="#123456" stroke="#654321" />')
    metadata = parser.preserve_metadata(element)
    assert metadata['id'] == 'test_id'
    assert metadata['style'] == 'fill:red;'
    assert metadata['transform'] == 'translate(10,10)'
    assert metadata['fill'] == '#123456'
    assert metadata['stroke'] == '#654321'


def test_path_with_hole_produces_donut_geometry():
    parser = SVGParser()
    # Inner ring wound opposite to the outer ring: a hole under nonzero (default).
    geometry = parser.path_to_polygon(
        "M 0 0 L 100 0 L 100 100 L 0 100 Z M 25 25 L 25 75 L 75 75 L 75 25 Z"
    )
    # Outer 100x100 minus inner 50x50 hole.
    assert abs(geometry.area - 7500) < 1


def test_path_nonzero_same_winding_subpaths_union():
    parser = SVGParser()
    # Two overlapping same-winding squares: nonzero fills the union (no hole).
    geometry = parser.path_to_polygon(
        "M 0 0 L 10 0 L 10 10 L 0 10 Z M 5 5 L 15 5 L 15 15 L 5 15 Z"
    )
    assert abs(geometry.area - 175) < 1


def test_path_evenodd_same_winding_subpaths_punch_hole():
    parser = SVGParser()
    geometry = parser.path_to_polygon(
        "M 0 0 L 100 0 L 100 100 L 0 100 Z M 25 25 L 75 25 L 75 75 L 25 75 Z",
        fill_rule="evenodd",
    )
    assert abs(geometry.area - 7500) < 1


def test_fill_rule_read_from_element_attribute():
    from lxml import etree
    parser = SVGParser()
    element = etree.fromstring(
        '<path d="M 0 0 L 100 0 L 100 100 L 0 100 Z M 25 25 L 75 25 L 75 75 L 25 75 Z" '
        'fill-rule="evenodd" />'
    )
    geometry = parser.convert_to_polygon(element)
    assert abs(geometry.area - 7500) < 1


def test_path_with_disjoint_subpaths_keeps_both_contours():
    parser = SVGParser()
    geometry = parser.path_to_polygon(
        "M 0 0 L 10 0 L 10 10 L 0 10 Z M 50 50 L 60 50 L 60 60 L 50 60 Z"
    )
    assert abs(geometry.area - 200) < 1


def test_curved_path_is_sampled_not_collapsed_to_endpoints():
    parser = SVGParser()
    geometry = parser.path_to_polygon("M 0 0 Q 50 100 100 0 Z")
    # Area under the quadratic arc is 2/3 * 100 * 50 = ~3333.
    assert 3000 < geometry.area < 3600


def test_transform_translate_applied_to_geometry(tmp_path):
    svg_content = """
    <svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
      <g transform="translate(50, 0)">
        <rect x="0" y="0" width="10" height="10" />
      </g>
    </svg>
    """
    file_path = tmp_path / "transform.svg"
    file_path.write_text(svg_content)

    parser = SVGParser()
    shapes, _, _ = parser.load_svg(str(file_path))
    assert len(shapes) == 1
    assert shapes[0].geometry.bounds == (50.0, 0.0, 60.0, 10.0)


def test_transform_on_path_drops_stale_d_attribute(tmp_path):
    svg_content = """
    <svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
      <path d="M 0 0 L 10 0 L 10 10 L 0 10 Z" transform="translate(5, 5)" />
      <path d="M 0 0 L 10 0 L 10 10 L 0 10 Z" />
    </svg>
    """
    file_path = tmp_path / "transform_path.svg"
    file_path.write_text(svg_content)

    parser = SVGParser()
    shapes, _, _ = parser.load_svg(str(file_path))
    assert len(shapes) == 2
    transformed, untouched = shapes
    assert transformed.d_attribute is None
    assert transformed.geometry.bounds == (5.0, 5.0, 15.0, 15.0)
    assert untouched.d_attribute
    assert untouched.geometry.bounds == (0.0, 0.0, 10.0, 10.0)


def test_transform_rotate_about_center():
    parser = SVGParser()
    matrix = parser.parse_transform("rotate(90, 10, 10)")
    geometry, transformed = parser.apply_transform(box(10, 10, 20, 20), matrix)
    assert transformed
    minx, miny, maxx, maxy = geometry.bounds
    assert abs(minx - 0) < 1e-6
    assert abs(miny - 10) < 1e-6
    assert abs(maxx - 10) < 1e-6
    assert abs(maxy - 20) < 1e-6


def test_viewbox_defines_coordinate_canvas(tmp_path):
    # width/height in mm, but shape coordinates live in the 1000x800 viewBox.
    svg_content = """
    <svg width="100mm" height="80mm" viewBox="0 0 1000 800" xmlns="http://www.w3.org/2000/svg">
      <rect x="900" y="700" width="50" height="50" />
    </svg>
    """
    file_path = tmp_path / "viewbox.svg"
    file_path.write_text(svg_content)

    parser = SVGParser()
    shapes, width, height = parser.load_svg(str(file_path))
    assert (width, height) == (1000, 800)
    assert shapes[0].geometry.bounds == (900, 700, 950, 750)


def test_polyline_is_filled_as_closed_polygon():
    from lxml import etree
    parser = SVGParser()
    element = etree.fromstring('<polyline points="0,0 10,0 10,10 0,10" />')
    polygon = parser.convert_to_polygon(element)
    assert polygon.area == 100


def test_defs_content_is_not_rendered_directly(tmp_path):
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <rect id="tpl" x="0" y="0" width="10" height="10" />
      </defs>
      <circle cx="50" cy="50" r="10" />
    </svg>
    """
    file_path = tmp_path / "defs.svg"
    file_path.write_text(svg_content)

    parser = SVGParser()
    shapes, _, _ = parser.load_svg(str(file_path))
    assert len(shapes) == 1


def test_use_instantiates_target_with_offset(tmp_path):
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink">
      <defs>
        <rect id="tpl" x="0" y="0" width="10" height="10" />
      </defs>
      <use xlink:href="#tpl" x="30" y="40" />
      <use href="#tpl" x="60" y="0" transform="translate(0, 5)" />
    </svg>
    """
    file_path = tmp_path / "use.svg"
    file_path.write_text(svg_content)

    parser = SVGParser()
    shapes, _, _ = parser.load_svg(str(file_path))
    assert len(shapes) == 2
    bounds = sorted(shape.geometry.bounds for shape in shapes)
    assert bounds[0] == (30, 40, 40, 50)
    assert bounds[1] == (60, 5, 70, 15)


def test_native_shape_captured_for_untransformed_elements(tmp_path):
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <circle cx="20" cy="20" r="10" />
      <circle cx="60" cy="60" r="10" transform="translate(5, 0)" />
      <rect x="0" y="0" width="10" height="10" rx="3" />
    </svg>
    """
    file_path = tmp_path / "native.svg"
    file_path.write_text(svg_content)

    parser = SVGParser()
    shapes, _, _ = parser.load_svg(str(file_path))
    assert shapes[0].native_shape == {'tag': 'circle', 'attrs': {'cx': '20', 'cy': '20', 'r': '10'}}
    # Transformed elements must not carry native markup.
    assert shapes[1].native_shape is None
    # Rounded rects re-emit natively now that their geometry is analyzed correctly.
    assert shapes[2].native_shape == {
        'tag': 'rect',
        'attrs': {'x': '0', 'y': '0', 'width': '10', 'height': '10', 'rx': '3'},
    }


def test_native_shape_skipped_for_unit_suffixed_attributes():
    from lxml import etree
    parser = SVGParser()
    element = etree.fromstring('<rect x="0" y="0" width="10mm" height="10mm" />')
    assert parser._native_shape(element, 'rect') is None


def test_native_shape_kept_for_zero_corner_radius():
    from lxml import etree
    parser = SVGParser()
    element = etree.fromstring('<rect x="0" y="0" width="10" height="10" rx="0" />')
    native = parser._native_shape(element, 'rect')
    assert native == {'tag': 'rect', 'attrs': {'x': '0', 'y': '0', 'width': '10', 'height': '10', 'rx': '0'}}


def test_rounded_rect_geometry_matches_expected_area():
    from lxml import etree
    parser = SVGParser()
    element = etree.fromstring('<rect x="0" y="0" width="100" height="60" rx="10" />')
    polygon = parser.convert_to_polygon(element)
    # Area = w*h - (4 - pi) * rx * ry = 6000 - (4 - pi) * 100 = ~5914.2
    expected = 100 * 60 - (4 - 3.14159265) * 10 * 10
    assert abs(polygon.area - expected) < 5
    # The bounding box is unchanged; corners are cut.
    assert polygon.bounds == (0, 0, 100, 60)
    from shapely.geometry import Point
    assert not polygon.contains(Point(1, 1))       # corner cut away
    assert polygon.contains(Point(50, 30))         # center intact


def test_rounded_rect_radii_clamped_and_defaulted():
    from lxml import etree
    parser = SVGParser()
    # ry omitted -> equals rx; rx larger than half width -> clamped.
    element = etree.fromstring('<rect x="0" y="0" width="20" height="40" rx="50" />')
    rx, ry = parser._rect_corner_radii(element, 20, 40)
    assert rx == 10  # clamped to width/2
    assert ry == 20  # defaulted to rx, clamped to height/2
    polygon = parser.convert_to_polygon(element)
    assert polygon.is_valid
    assert polygon.bounds == (0, 0, 20, 40)


def test_fill_inherited_from_ancestor_group(tmp_path):
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <g fill="#123456">
        <rect x="0" y="0" width="10" height="10" />
        <rect x="20" y="0" width="10" height="10" fill="#ff0000" />
      </g>
      <g style="fill: rgb(1,2,3);">
        <rect x="40" y="0" width="10" height="10" />
      </g>
    </svg>
    """
    file_path = tmp_path / "inherit.svg"
    file_path.write_text(svg_content)

    parser = SVGParser()
    shapes, _, _ = parser.load_svg(str(file_path))
    assert shapes[0].metadata['fill'] == '#123456'      # inherited
    assert shapes[1].metadata['fill'] == '#ff0000'      # own wins
    assert shapes[2].metadata['fill'] == 'rgb(1,2,3)'   # inherited from style


def test_stroke_footprint_grows_geometry(tmp_path):
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <rect x="10" y="10" width="10" height="10" stroke="#000" stroke-width="4" />
      <rect x="40" y="10" width="10" height="10" />
    </svg>
    """
    file_path = tmp_path / "stroke.svg"
    file_path.write_text(svg_content)

    plain_shapes, _, _ = SVGParser().load_svg(str(file_path))
    stroked_shapes, _, _ = SVGParser(include_strokes=True).load_svg(str(file_path))

    # Stroked rect grows by stroke-width/2 on each side; unstroked is untouched.
    assert plain_shapes[0].geometry.bounds == (10, 10, 20, 20)
    assert stroked_shapes[0].geometry.bounds == (8, 8, 22, 22)
    assert stroked_shapes[1].geometry.bounds == (40, 10, 50, 20)
    # Grown geometry no longer matches original markup.
    assert stroked_shapes[0].native_shape is None
    assert stroked_shapes[1].native_shape is not None


def test_stroke_footprint_creates_conflicts_between_near_shapes(tmp_path):
    # Two rects 2 units apart; 4-unit strokes make their footprints overlap.
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <g stroke="#000" stroke-width="4">
        <rect x="0" y="0" width="10" height="10" />
        <rect x="12" y="0" width="10" height="10" />
      </g>
    </svg>
    """
    file_path = tmp_path / "stroke_conflict.svg"
    file_path.write_text(svg_content)

    from geometry_engine import GeometryEngine
    engine = GeometryEngine(use_spatial_index=True)

    plain_shapes, _, _ = SVGParser().load_svg(str(file_path))
    assert engine.detect_overlaps(plain_shapes) == []

    stroked_shapes, _, _ = SVGParser(include_strokes=True).load_svg(str(file_path))
    assert len(engine.detect_overlaps(stroked_shapes)) == 1
