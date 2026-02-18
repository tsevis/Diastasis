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
    element = etree.fromstring('<rect id="test_id" style="fill:red;" transform="translate(10,10)" />')
    metadata = parser.preserve_metadata(element)
    assert metadata['id'] == 'test_id'
    assert metadata['style'] == 'fill:red;'
    assert metadata['transform'] == 'translate(10,10)'