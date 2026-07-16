import os

import pytest

from diastasis.cli import main


SIMPLE_SVG = """
<svg width="40" height="40" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="20" height="20" fill="#ff0000" />
  <rect x="10" y="0" width="20" height="20" fill="#00ff00" />
</svg>
"""


@pytest.fixture
def svg_file(tmp_path):
    path = tmp_path / "art.svg"
    path.write_text(SIMPLE_SVG)
    return str(path)


def test_cli_processes_single_file(svg_file, tmp_path, capsys):
    outdir = str(tmp_path / "out")
    assert main([svg_file, "-o", outdir]) == 0
    assert os.path.exists(os.path.join(outdir, "art_layered.svg"))
    assert "Used" in capsys.readouterr().out


def test_cli_separate_files(svg_file, tmp_path):
    outdir = str(tmp_path / "out")
    assert main([svg_file, "-o", outdir, "--mode", "flat", "--separate-files", "-q"]) == 0
    layer_files = [f for f in os.listdir(outdir) if "_layer_" in f]
    assert len(layer_files) >= 2


def test_cli_batch_mode(tmp_path):
    indir = tmp_path / "in"
    indir.mkdir()
    for name in ("a.svg", "b.svg"):
        (indir / name).write_text(SIMPLE_SVG)
    outdir = str(tmp_path / "out")

    assert main(["--batch", str(indir), "-o", outdir, "-q"]) == 0
    assert os.path.exists(os.path.join(outdir, "a_layered.svg"))
    assert os.path.exists(os.path.join(outdir, "b_layered.svg"))


def test_cli_estimate_only(svg_file, tmp_path, capsys):
    assert main([svg_file, "--estimate"]) == 0
    out = capsys.readouterr().out
    assert "2 shapes" in out
    assert not os.path.exists("output/art_layered.svg")


def test_cli_rejects_missing_input_choice():
    assert main([]) == 2


def test_cli_rejects_both_input_and_batch(svg_file, tmp_path):
    assert main([svg_file, "--batch", str(tmp_path)]) == 2


def test_cli_force_k_requires_num_layers(svg_file):
    assert main([svg_file, "--algorithm", "force_k"]) == 2


def test_cli_missing_file_errors(tmp_path):
    assert main([str(tmp_path / "nope.svg")]) == 2


def test_cli_estimate_missing_file_returns_error_code():
    assert main(["/no/such/file.svg", "--estimate"]) == 2


def test_cli_batch_continues_past_malformed_file(tmp_path, capsys):
    indir = tmp_path / "in"
    indir.mkdir()
    (indir / "good.svg").write_text(SIMPLE_SVG)
    (indir / "bad.svg").write_text("<svg not well formed")
    outdir = str(tmp_path / "out")

    exit_code = main(["--batch", str(indir), "-o", outdir, "-q"])

    # The bad file fails, the good file still processes, exit code reports failure.
    assert exit_code == 1
    assert os.path.exists(os.path.join(outdir, "good_layered.svg"))
    assert "bad.svg" in capsys.readouterr().err
