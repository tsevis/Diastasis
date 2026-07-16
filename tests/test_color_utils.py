import pytest

from diastasis.color_utils import color_distance, parse_color, rgb_to_hex


@pytest.mark.parametrize(
    "value, expected",
    [
        ("#f00", (255, 0, 0)),
        ("#FF0000", (255, 0, 0)),
        ("#00ff00", (0, 255, 0)),
        ("rgb(0,0,255)", (0, 0, 255)),
        ("rgb(100%, 0%, 0%)", (255, 0, 0)),
        ("rgba(255, 255, 255, 0.5)", (255, 255, 255)),
        ("RED", (255, 0, 0)),
        ("RebeccaPurple", (102, 51, 153)),
        ("  #abc  ", (170, 187, 204)),
    ],
)
def test_parse_color_valid_forms(value, expected):
    assert parse_color(value) == expected


@pytest.mark.parametrize("value", [None, "", "none", "transparent", "notacolor", "#12", "rgb(1,2)", "#gggggg"])
def test_parse_color_rejects_unusable(value):
    assert parse_color(value) is None


def test_color_distance_and_hex_roundtrip():
    assert color_distance((0, 0, 0), (0, 0, 0)) == 0
    assert color_distance((255, 0, 0), (0, 0, 255)) == pytest.approx(360.62, abs=0.1)
    assert rgb_to_hex((170, 187, 204)) == "#AABBCC"
    assert parse_color(rgb_to_hex((12, 34, 56))) == (12, 34, 56)
