# Diastasis - SVG Layer Separation Tool

Diastasis separates complex SVG artwork into production-ready layers.

## Features

- Two modes:
  - `Overlaid Complexity`: overlap-aware layering.
  - `Flat Complexity`: strict area-exclusive separation.
- Quality presets:
  - `Accurate`, `Balanced`, `Fast`.
- Complexity estimator:
  - shape count, candidate pairs, graph density, ETA.
- Batch mode:
  - process all `.svg` files in a folder with current settings.
- Export profiles:
  - `Illustrator-safe`, `Print`, `Web`.
- Visible-boundary clipping (`Clip Shapes To Visible Boundaries`).
- Performance mode for weaker systems / huge files.
- Flat controls:
  - touch policy (`No edge/corner touching`, `Allow corner touching`)
  - overlap priority (`Source order`, `Largest first`, `Smallest first`)
- Layer analytics in summary:
  - overlap/conflict count
  - tiny fragment count
  - per-layer area share

## Installation

```bash
git clone https://github.com/tsevis/Diastasis.git
cd Diastasis
pip install -r requirements.txt
```

## Run

```bash
python gui.py
```

or:

```bash
./run_gui.sh
```

## Typical Workflow

1. Click `Select SVG`.
2. Choose `Quality Preset` and `Export Profile`.
3. Click `Estimate Complexity` (recommended for heavy files).
4. Choose mode (`Overlaid Complexity` or `Flat Complexity`).
5. Set optional controls:
   - `Clip Shapes To Visible Boundaries`
   - `Performance Mode`
6. Click `Process`.
7. Export with:
   - `Save Layers As...`
   - `Save Clipped 1-Layer As...`

## Batch Workflow

1. Configure settings as desired (mode, preset, profile, clipping, etc.).
2. Click `Batch Process Folder`.
3. Choose input folder (SVG files).
4. Choose output folder.

Each file is processed with the same active settings.

## Export Profiles

- `Illustrator-safe`: balanced precision, crop marks included.
- `Print`: higher path precision, crop marks included.
- `Web`: lower precision, no crop marks.

## Programmatic Usage

```python
from main import run_diastasis, save_layers_to_files

shapes, coloring, summary, w, h = run_diastasis(
    "input.svg",
    mode="flat",
    flat_algorithm="DSATUR",
    flat_touch_policy="any_touch",
    flat_priority_order="source",
    clip_visible_boundaries=True,
    performance_mode=False,
)

save_layers_to_files(
    shapes,
    coloring,
    "output",
    "job",
    w,
    h,
    preserve_original_colors=True,
    export_profile="Illustrator-safe",
)
```

## License

MIT
