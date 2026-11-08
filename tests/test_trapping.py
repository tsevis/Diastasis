import pytest
from shapely.geometry import box

from diastasis.main import run_diastasis
from diastasis.svg_parser import Shape
from diastasis.trapping import trap_plates

YELLOW = "#ffff00"
BLUE = "#0000ff"


def _shape(idx, geometry, fill):
    return Shape(id=idx, geometry=geometry, metadata={"fill": fill}, d_attribute="M0 0")


def _two_abutting_plates(left_fill, right_fill):
    """Two plates whose shapes share the edge x=10."""
    shapes = [
        _shape(0, box(0, 0, 10, 10), left_fill),
        _shape(1, box(10, 0, 20, 10), right_fill),
    ]
    grouped = {0: [0], 1: [1]}
    inks = {0: left_fill, 1: right_fill}
    return shapes, grouped, inks


@pytest.mark.parametrize("light_on_left", [True, False])
def test_lighter_ink_spreads_under_darker_ink_whichever_side_it_is_on(light_on_left):
    # Catches: the dark ink spreading instead (moving the visible edge), or the
    # direction depending on position/plate id rather than on lightness.
    left, right = (YELLOW, BLUE) if light_on_left else (BLUE, YELLOW)
    shapes, grouped, inks = _two_abutting_plates(left, right)

    out = trap_plates(shapes, grouped, inks, width=1.0)

    light, dark = (out[0], out[1]) if light_on_left else (out[1], out[0])
    assert light.geometry.area == pytest.approx(110.0)
    assert dark.geometry.area == pytest.approx(100.0)
    assert dark.geometry.equals(shapes[1 if light_on_left else 0].geometry)


def test_spread_stops_at_the_dark_shape_and_never_reaches_bare_paper():
    # Catches: buffering the light shape without clipping to the dark footprint,
    # which would grow the silhouette by the full width into paper.
    shapes = [
        _shape(0, box(0, 0, 10, 10), YELLOW),
        _shape(1, box(10, 0, 10.4, 10), BLUE),  # thinner than the trap width
    ]
    out = trap_plates(shapes, {0: [0], 1: [1]}, {0: YELLOW, 1: BLUE}, width=1.0)

    assert out[0].geometry.bounds == pytest.approx((0.0, 0.0, 10.4, 10.0))


def test_plate_order_option_lets_the_press_order_decide_instead_of_lightness():
    # Catches: ignoring `order`, so a printer who runs blue first still gets
    # yellow spreading under blue.
    shapes, grouped, inks = _two_abutting_plates(BLUE, YELLOW)

    out = trap_plates(shapes, grouped, inks, width=1.0, order="plate")

    assert out[0].geometry.area == pytest.approx(110.0)  # plate 0 (blue) prints first
    assert out[1].geometry.area == pytest.approx(100.0)


def test_shapes_on_the_same_plate_do_not_trap_each_other():
    # Catches: treating same-ink neighbours as a different ink and fattening
    # every internal seam.
    shapes = [
        _shape(0, box(0, 0, 10, 10), YELLOW),
        _shape(1, box(10, 0, 20, 10), YELLOW),
    ]
    out = trap_plates(shapes, {0: [0, 1]}, {0: YELLOW}, width=1.0)

    assert out[0].geometry.equals(shapes[0].geometry)
    assert out[1].geometry.equals(shapes[1].geometry)


def test_plate_with_no_resolvable_fill_is_left_alone_and_does_not_crash():
    # Catches: a None ink crashing the lightness ranking, or an unknown ink
    # being trapped as if it were rankable.
    shapes = [
        _shape(0, box(0, 0, 10, 10), YELLOW),
        Shape(id=1, geometry=box(10, 0, 20, 10), metadata={}),
    ]
    out = trap_plates(shapes, {0: [0], 1: [1]}, {0: YELLOW, 1: None}, width=1.0)

    assert out[0].geometry.equals(shapes[0].geometry)
    assert out[1].geometry.equals(shapes[1].geometry)


def test_untouched_shapes_keep_their_original_markup_and_input_is_not_mutated():
    # Catches: dropping d_attribute on shapes the trap never changed, and
    # mutating the caller's shapes in place.
    shapes, grouped, inks = _two_abutting_plates(YELLOW, BLUE)
    before = [s.geometry for s in shapes]

    out = trap_plates(shapes, grouped, inks, width=1.0)

    assert out[1].d_attribute == "M0 0"  # the dark shape never changed
    assert out[0].d_attribute is None  # geometry changed, so old markup is stale
    assert [s.geometry for s in shapes] == before


def test_negative_width_is_rejected():
    shapes, grouped, inks = _two_abutting_plates(YELLOW, BLUE)
    with pytest.raises(ValueError):
        trap_plates(shapes, grouped, inks, width=-1.0)


def _abutting_svg(tmp_path):
    svg = tmp_path / "abut.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10" width="20" height="10">'
        f'<rect x="0" y="0" width="10" height="10" fill="{YELLOW}"/>'
        f'<rect x="10" y="0" width="10" height="10" fill="{BLUE}"/>'
        "</svg>"
    )
    return svg


def test_trap_outside_colour_mode_is_refused_not_silently_ignored(tmp_path):
    # Catches: a trap request in flat/overlaid mode quietly producing untrapped
    # plates, so the user ships them believing they are trapped.
    result = run_diastasis(str(_abutting_svg(tmp_path)), mode="flat", trap_width=1.0)

    assert result[0] is None
    assert "color" in result[2].lower()


def test_cli_trap_width_end_to_end_and_fails_fast_outside_colour_mode(tmp_path, capsys):
    # Catches: the flag not reaching the pipeline, or exiting 0 with untrapped plates.
    from diastasis.cli import main

    svg = _abutting_svg(tmp_path)
    out = str(tmp_path / "out")

    assert main([str(svg), "-o", out, "--mode", "color", "--trap-width", "1"]) == 0
    assert "Trapping: 1 shapes" in capsys.readouterr().out
    assert main([str(svg), "-o", out, "--mode", "flat", "--trap-width", "1"]) == 2
    assert main([str(svg), "-o", out, "--mode", "color", "--trap-width", "-1"]) == 2


def test_run_diastasis_traps_colour_plates_end_to_end(tmp_path):
    # Catches: the option not being wired through the colour pipeline.
    svg = _abutting_svg(tmp_path)

    shapes, grouped, summary, _, _ = run_diastasis(str(svg), mode="color", trap_width=1.0)

    areas = sorted(round(s.geometry.area, 3) for s in shapes)
    assert areas == [100.0, 110.0]
    assert "trap" in summary.lower()
