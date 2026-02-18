# Diastasis - SVG Layer Separation Tool

Diastasis separates complex SVG artwork into production-ready layers.
It supports strict area-exclusion workflows, optional visible-boundary clipping, and configurable Flat/Overlaid strategies for heavy real-world files.

## Features

- Two processing modes:
  - **Overlaid Complexity**: overlap-aware graph coloring for layered output.
  - **Flat Complexity**: area-exclusive separation with configurable adjacency constraints.
- Shared GUI workflow: one file picker + one preview across both modes.
- Multiple coloring algorithms: `largest_first`, `smallest_last`, `independent_set`, `DSATUR`, `random_sequential`, `connected_sequential_bfs`, `connected_sequential_dfs`, `force_k`.
- Flat touch policies:
  - `No edge/corner touching` (strict)
  - `Allow corner touching` (point-only corner contacts may share a layer)
- Flat overlap priority:
  - `Source order` (SVG visual stack aware)
  - `Largest first`
  - `Smallest first`
- **Visible boundary clipping**: clip each shape to only the area actually visible in stacked SVG artwork.
- **Original color preservation with clipping**:
  - clipped exports preserve shape fill colors from SVG metadata/style.
- Flat `force_k` is soft-constrained:
  - if `k` is too low, it still runs and minimizes conflicts.
  - summary reports lower bound + conflict count.
- Export options:
  - `Save Layers As...` (multi-layer SVG)
  - `Save Clipped 1-Layer As...` (single-layer clipped SVG)
- Crop marks generation in layered export.
- Performance improvements for heavy files:
  - faster bounds checks
  - reduced duplicate graph builds
  - safer recursion fallback in coloring strategies

## Installation

```bash
git clone https://github.com/tsevis/Diastasis.git
cd Diastasis
pip install -r requirements.txt
```

## Usage

### GUI

```bash
python gui.py
```

or

```bash
./run_gui.sh
```

### Typical workflow

1. Select SVG.
2. Choose mode (`Overlaid Complexity` or `Flat Complexity`).
3. Optional: enable `Clip Shapes To Visible Boundaries`.
4. Set mode-specific options.
5. Click `Process`.
6. Export:
   - `Save Layers As...`
   - `Save Clipped 1-Layer As...`

## Flat Complexity Notes

### Touch policy

- `No edge/corner touching`: any contact is a conflict.
- `Allow corner touching`: corner-only point contacts are allowed.

### Overlap priority

Controls who keeps contested area during flattening:

- `Source order`: top-most SVG paint order wins.
- `Largest first`: larger regions are preserved first.
- `Smallest first`: detail shapes are preserved first.

### force_k behavior

`force_k` in Flat mode allows conflicts when needed and minimizes them.
Summary includes:

- minimum proven required layers
- `force_k` target
- conflict pairs introduced

## Programmatic usage

```python
from main import run_diastasis, save_layers_to_files, save_single_layer_file

shapes, coloring, summary, w, h = run_diastasis(
    "input.svg",
    mode="flat",
    flat_algorithm="DSATUR",
    flat_touch_policy="any_touch",        # or "edge_or_overlap"
    flat_priority_order="source",         # or "largest_first", "smallest_first"
    clip_visible_boundaries=True,
)

# Multi-layer export
save_layers_to_files(
    shapes,
    coloring,
    "output",
    "job",
    w,
    h,
    preserve_original_colors=True,
)

# Single-layer clipped export
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

MIT (see `LICENSE` if present in repository).
