from shapely.geometry import box

from diastasis.main import run_diastasis
from diastasis.svg_export import (
    save_layers_to_files,
    save_layers_to_separate_files,
    shape_element_markup,
)
from diastasis.svg_parser import Shape


def test_shape_element_markup_prefers_original_path_data():
    shape = Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}, d_attribute="M 0 0 L 10 0 L 10 10 L 0 10 Z")
    markup = shape_element_markup(shape, fill="#112233")
    assert 'd="M 0 0 L 10 0 L 10 10 L 0 10 Z"' in markup
    assert 'fill="#112233"' in markup


def test_shape_element_markup_uses_native_element():
    shape = Shape(
        id=0,
        geometry=box(0, 0, 10, 10),
        metadata={},
        native_shape={"tag": "circle", "attrs": {"cx": "5", "cy": "5", "r": "5"}},
    )
    markup = shape_element_markup(shape, fill="#000000")
    assert markup.startswith("<circle ")
    assert 'cx="5"' in markup and 'r="5"' in markup


def test_shape_element_markup_falls_back_to_generated_path():
    donut = box(0, 0, 100, 100).difference(box(25, 25, 75, 75))
    shape = Shape(id=0, geometry=donut, metadata={})
    markup = shape_element_markup(shape, fill="#000000")
    assert markup.startswith("<path ")
    assert 'fill-rule="evenodd"' in markup


def test_native_elements_survive_end_to_end_export(tmp_path):
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <circle cx="30" cy="30" r="20" fill="#ff0000" />
      <rect x="60" y="60" width="30" height="30" fill="#00ff00" />
    </svg>
    """
    svg_file = tmp_path / "native_e2e.svg"
    svg_file.write_text(svg_content)

    shapes, grouped, _, w, h = run_diastasis(str(svg_file), mode="overlaid")
    save_layers_to_files(shapes, grouped, str(tmp_path), "native_e2e", w, h, preserve_original_colors=True)

    content = (tmp_path / "native_e2e_layered.svg").read_text()
    # Overlaid mode leaves geometry untouched, so original elements re-emit
    # natively instead of as polygonized approximations.
    assert '<circle cx="30" cy="30" r="20"' in content
    assert '<rect x="60" y="60" width="30" height="30"' in content
    assert 'fill="#ff0000"' in content


def test_save_layers_to_separate_files_registers_layers(tmp_path):
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(5, 0, 15, 10), metadata={}),
    ]
    coloring = {0: [0], 1: [1]}

    written = save_layers_to_separate_files(
        shapes, coloring, str(tmp_path), "job", 100, 100, export_profile="Print"
    )

    assert len(written) == 2
    for position, filepath in enumerate(written, start=1):
        content = open(filepath).read()
        assert f'data-layer="{position}"' in content
        assert 'data-layer-total="2"' in content
        assert 'viewBox="0 0 100 100"' in content
        # Crop marks keep separate layer files in register.
        assert 'id="Crop_Marks"' in content


def test_save_layers_to_separate_files_web_profile_omits_crop_marks(tmp_path):
    shapes = [Shape(id=0, geometry=box(0, 0, 10, 10), metadata={})]
    written = save_layers_to_separate_files(
        shapes, {0: [0]}, str(tmp_path), "job", 100, 100, export_profile="Web"
    )
    content = open(written[0]).read()
    assert 'id="Crop_Marks"' not in content


def test_export_escapes_malicious_attribute_values(tmp_path):
    # An entity-encoded fill attribute must not inject markup into the output.
    svg_content = (
        '<svg width="40" height="40" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="0" y="0" width="20" height="20" '
        'fill="red&quot;/&gt;&lt;script&gt;alert(1)&lt;/script&gt;&lt;rect fill=&quot;blue" />'
        '<rect x="10" y="0" width="20" height="20" fill="#00ff00" />'
        "</svg>"
    )
    svg_file = tmp_path / "evil.svg"
    svg_file.write_text(svg_content)

    shapes, grouped, _, w, h = run_diastasis(str(svg_file), mode="overlaid")
    save_layers_to_files(shapes, grouped, str(tmp_path), "evil", w, h, preserve_original_colors=True)

    content = (tmp_path / "evil_layered.svg").read_text()
    assert "<script" not in content

    # The output must still be well-formed XML.
    from lxml import etree
    etree.fromstring(content.encode())


def test_shape_element_markup_escapes_native_attrs_and_fill():
    shape = Shape(
        id=0,
        geometry=box(0, 0, 10, 10),
        metadata={},
        native_shape={"tag": "circle", "attrs": {"cx": '5"/><evil', "cy": "5", "r": "5"}},
    )
    markup = shape_element_markup(shape, fill='red"><evil')
    assert "<evil" not in markup
