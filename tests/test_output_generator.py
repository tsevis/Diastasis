import pytest
import os
from output_generator import OutputGenerator
from svg_parser import Shape
from shapely.geometry import Polygon, box
import networkx as nx # For coloring dictionary

# Fixture for creating simple shapes
@pytest.fixture
def simple_shapes():
    shape1 = Shape(id=0, geometry=box(0, 0, 10, 10), metadata={'style': 'fill:red;', 'id': 's1'})
    shape2 = Shape(id=1, geometry=box(5, 5, 15, 15), metadata={'style': 'fill:blue;', 'id': 's2'})
    shape3 = Shape(id=2, geometry=box(20, 20, 30, 30), metadata={'style': 'fill:green;', 'id': 's3'})
    return [shape1, shape2, shape3]

# Fixture for a coloring dictionary
@pytest.fixture
def simple_coloring():
    # Example: shape 0 and 2 in layer 0, shape 1 in layer 1
    return {0: 0, 1: 1, 2: 0}

def test_create_layer_files(tmp_path, simple_shapes, simple_coloring):
    output_dir = tmp_path / "output_layers"
    original_filename = "test_design"
    
    generator = OutputGenerator()
    generator.create_layer_files(simple_shapes, simple_coloring, str(output_dir), original_filename)
    
    # Check if directories and files are created
    assert os.path.exists(output_dir)
    assert os.path.exists(output_dir / f"{original_filename}_layer_1.svg")
    assert os.path.exists(output_dir / f"{original_filename}_layer_2.svg")
    assert not os.path.exists(output_dir / f"{original_filename}_layer_3.svg") # Only 2 layers in simple_coloring

    # Check content of layer 1 (shapes 0 and 2)
    with open(output_dir / f"{original_filename}_layer_1.svg", "r") as f:
        content = f.read()
        assert "<svg" in content
        assert "</svg>" in content
        assert 'id="s1"' in content or 'id="s3"' in content # Check for shape IDs
        assert 'id="s2"' not in content # Shape 2 should not be in layer 1
        assert "fill:rgb(" in content # Check for random color
        assert "<line x1=" in content # Check for registration marks

    # Check content of layer 2 (shape 1)
    with open(output_dir / f"{original_filename}_layer_2.svg", "r") as f:
        content = f.read()
        assert "<svg" in content
        assert "</svg>" in content
        assert 'id="s2"' in content # Check for shape ID
        assert 'id="s1"' not in content # Shape 1 should not be in layer 2
        assert "fill:rgb(" in content # Check for random color
        assert "<line x1=" in content # Check for registration marks

def test_generate_svg_layer(simple_shapes):
    generator = OutputGenerator()
    layer_color = "fill:rgb(100,100,100);"
    svg_content = generator.generate_svg_layer(
        [simple_shapes[0]], 0, simple_shapes, layer_color, "test_file"
    )
    assert "<svg" in svg_content
    assert "</svg>" in svg_content
    assert 'id="s1"' in svg_content
    assert layer_color in svg_content
    assert "<line x1=" in svg_content # Check for cross marks
    assert "<text" in svg_content # Check for layer name

def test_to_svg_path(simple_shapes):
    generator = OutputGenerator()
    color = "fill:rgb(200,50,10);"
    path_str = generator.to_svg_path(simple_shapes[0], color)
    assert 'd="' in path_str # Check that d attribute is present
    assert 'M ' in path_str # Check that it starts with M
    assert ' Z"' in path_str # Check that it ends with Z
    assert color in path_str
    assert 'id="s1"' in path_str

def test_add_registration_marks(simple_shapes):
    generator = OutputGenerator()
    marks = generator.add_registration_marks(simple_shapes, "my_layer")
    assert len(marks) == 9 # 8 lines for crosses + 1 text for layer name
    assert "<line" in marks[0]
    assert "<text" in marks[8]
    assert "my_layer" in marks[8]

def test_create_summary_report(simple_shapes, simple_coloring):
    generator = OutputGenerator()
    summary = generator.create_summary_report(
        simple_coloring, simple_shapes, "output_dir", "original_file", 1.23, 0.45
    )
    assert "Mozaix Diastasis - Shape Separation Report" in summary
    assert "Input file: original_file.svg" in summary
    assert "Total shapes: 3" in summary
    assert "Number of layers created: 2" in summary
    assert "Processing time: 1.23 seconds" in summary
    assert "Memory usage: 0.45 GB" in summary
    assert "Layer 1: 2 shapes" in summary # Shapes 0 and 2
    assert "Layer 2: 1 shapes" in summary # Shape 1

def test_empty_coloring_for_summary():
    generator = OutputGenerator()
    summary = generator.create_summary_report({}, [], "output_dir", "original_file", 0, 0)
    assert summary == ""