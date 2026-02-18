# Diastasis - SVG Layer Separation Tool

**Diastasis** is an SVG processing tool that separates complex overlapping artwork into manufacturable layers.
It supports strict non-overlap workflows, configurable flat separation rules, and visible-boundary clipping for stacked SVG artwork.

## Features

- **Two processing modes**
  - **Overlaid Complexity**: classic overlap-graph separation for layered output.
  - **Flat Complexity**: area-exclusive separation with configurable touch rules.
- **Shared GUI workflow**: one file picker + one preview used across both modes.
- **Multiple graph-coloring algorithms**: `largest_first`, `smallest_last`, `independent_set`, `DSATUR`, `random_sequential`, `connected_sequential_bfs`, `connected_sequential_dfs`, `force_k`.
- **Flat touch policies**
  - `No edge/corner touching` (strict)
  - `Allow corner touching` (point-only corner contacts may share layer)
- **Flat overlap priority**
  - `Source order`
  - `Largest first`
  - `Smallest first`
- **Visible boundary clipping**: optional clipping of each shape to only its actually visible area based on SVG stacking.
- **Force-K in Flat mode**: allowed as a soft-constrained mode (can introduce conflict pairs when `k` is too small), with conflict stats reported.
- **Export options**
  - Multi-layer SVG export (`Save Layers As...`)
  - Single clipped layer SVG export (`Save Clipped 1-Layer As...`)
- **Crop marks generation** in layered export.
- **Efficient geometry processing** via Shapely + R-tree spatial indexing.

## Installation

1. Clone repository:

```bash
git clone https://github.com/tsevis/Diastasis.git
cd Diastasis
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### GUI (recommended)

```bash
python gui.py
```

Or:

```bash
./run_gui.sh
```

### GUI workflow

1. Select an SVG file.
2. Choose mode:
   - **Overlaid Complexity**
   - **Flat Complexity**
3. (Optional) Enable **Clip Shapes To Visible Boundaries**.
4. Configure algorithm/settings for the active mode.
5. Click **Process**.
6. Export with either:
   - **Save Layers As...**
   - **Save Clipped 1-Layer As...**

## Flat Complexity Details

Flat mode is designed for strict area exclusivity and controllable adjacency constraints.

### Touch Policy

- **No edge/corner touching**: any intersection/touch is treated as conflict.
- **Allow corner touching**: point-only corner contacts are allowed in same layer.

### Overlap Priority

Controls who keeps contested overlapping regions during flattening:

- **Source order**: follows SVG visual stacking (top-most keeps area).
- **Largest first**: larger shapes keep contested regions first.
- **Smallest first**: smaller/detail shapes keep contested regions first.

### Force-K behavior in Flat mode

`force_k` is intentionally **soft-constrained** in Flat mode:

- It targets exactly `k` layers.
- If `k` is below strict feasibility, it still runs and minimizes conflicts.
- Summary reports:
  - minimum proven required layers (clique lower bound)
  - target `k`
  - introduced conflict-pair count

## Programmatic Usage

```python
from main import run_diastasis, save_layers_to_files, save_single_layer_file

shapes, coloring, summary, w, h = run_diastasis(
    "input.svg",
    mode="flat",
    flat_algorithm="DSATUR",
    flat_touch_policy="any_touch",           # or "edge_or_overlap"
    flat_priority_order="source",            # or "largest_first", "smallest_first"
    clip_visible_boundaries=True,
)

save_layers_to_files(shapes, coloring, "output", "job", w, h)
save_single_layer_file(shapes, "output/job_single.svg", w, h)
```

## Dependencies

- `svgpathtools`
- `shapely`
- `rtree`
- `networkx`
- `numpy`
- `lxml`
- `Pillow`
- `cairosvg`

## License

MIT (see `LICENSE` if present in your repository).
