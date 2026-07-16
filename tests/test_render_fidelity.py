"""
Pixel-level fidelity check: a clipped (visible-boundaries) export must
render the same image as the input file. Skipped when cairosvg cannot
load its native cairo library (e.g. in CI without the gui extras).
"""
import io

import pytest

from diastasis.main import run_diastasis, save_single_layer_file


def _load_cairosvg():
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>')
        return cairosvg
    except (ImportError, OSError):
        return None


cairosvg = _load_cairosvg()
pytestmark = pytest.mark.skipif(cairosvg is None, reason="cairosvg unavailable")


def _render(svg_path: str, size: int = 200):
    from PIL import Image
    png = cairosvg.svg2png(url=svg_path, output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGB")


def test_clipped_single_layer_renders_like_input(tmp_path):
    svg_content = """
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="100" height="100" fill="#dddddd" />
      <rect x="10" y="10" width="50" height="50" fill="#cc2200" />
      <circle cx="60" cy="60" r="25" fill="#0044cc" />
      <path d="M 20 70 L 45 95 L 20 95 Z" fill="#00aa44" />
    </svg>
    """
    svg_in = tmp_path / "fidelity_in.svg"
    svg_in.write_text(svg_content)
    svg_out = tmp_path / "fidelity_out.svg"

    shapes, _, _, w, h = run_diastasis(str(svg_in), mode="overlaid", clip_visible_boundaries=True)
    save_single_layer_file(shapes, str(svg_out), w, h)

    image_in = _render(str(svg_in))
    image_out = _render(str(svg_out))

    total = image_in.width * image_in.height
    differing = sum(
        1
        for p_in, p_out in zip(image_in.getdata(), image_out.getdata())
        if max(abs(a - b) for a, b in zip(p_in, p_out)) > 40
    )
    # Antialiasing along clip seams differs slightly; the artwork must not.
    assert differing / total < 0.03, f"{differing}/{total} pixels differ"
