# Diastasis Manual

## Core Concepts

Diastasis has two processing models:

- `Overlaid Complexity`
  - Keeps overlap relationships and creates layers based on overlap conflicts.
- `Flat Complexity`
  - Enforces area-exclusive output (no shared area in final fragments).

Use Overlaid for classic layered decomposition.
Use Flat when strict non-overlap output is required.

## New Workflow Controls

## Quality Preset

- `Accurate`
  - Higher quality defaults, slower.
  - Uses `minimum_layers` (refinement built in).
- `Balanced`
  - Good default for most jobs.
- `Fast`
  - Prioritizes speed.
  - Enables performance mode.

## Complexity Report

`Estimate Complexity` computes:

- shape count
- candidate pair count
- graph density
- estimated processing time

Use it before heavy jobs to choose preset/mode.

## Performance Mode

For weaker systems or huge files:

- applies safe geometry simplification when file is large
- uses lighter overlap detection path where possible

Use only when speed is more important than exact geometric detail.

## Batch Process Folder

Processes all SVG files in a selected folder with current settings.

Steps:
1. Configure settings once.
2. Click `Batch Process Folder`.
3. Select input folder.
4. Select output folder.

## Flat-Specific Controls

## Touch Policy

- `No edge/corner touching`
  - any contact is conflict
- `Allow corner touching`
  - point-only corner contacts may share a layer

## Overlap Priority

Controls who keeps contested area in flat separation:

- `Source order`
- `Largest first`
- `Smallest first`

## Command Line Interface

For automation and headless use, the `diastasis` command (installed via
`pip install -e .`) exposes the full pipeline:

```bash
diastasis artwork.svg -o output/                 # one file
diastasis --batch folder/ -o output/             # whole folder
diastasis artwork.svg --mode flat --separate-files
diastasis artwork.svg --estimate                 # complexity only
diastasis artwork.svg --include-strokes          # stroke-aware footprints
```

`--separate-files` writes one SVG per layer on a shared canvas with crop
marks, so the files stay in register when stacked in production.

## Export Controls

## Save Layers As...

Creates a multi-layer SVG from processing result.

## Save Layers As Separate Files...

Writes one SVG file per layer, all on the same canvas with shared crop
marks, so the files stay in register when stacked in production.

## Save Clipped 1-Layer As...

Creates one flattened clipped SVG layer.

## Preserve Original Colors On Export

When enabled (default), exported shapes keep the artwork's own fills,
including fills inherited from groups. Disable to recolor each layer with
a distinct flat color for checking the separation.

## Export Profile

- `Illustrator-safe`
  - balanced path precision
  - crop marks included
- `Print`
  - higher path precision
  - crop marks included
- `Web`
  - smaller output (lower path precision)
  - crop marks disabled

## Results Analytics

Processing summary now includes:

- layers used
- overlap/conflict count
- tiny fragment count
- per-layer area share

Use these metrics to compare settings and reduce noisy outputs.

## Algorithm Notes

- `minimum_layers` (default) tries several coloring strategies, refines the
  best result, and (on small graphs) runs an exact search. The summary reports
  the proven minimum required layers and says when the result is provably
  optimal — that is the fewest layers possible for the artwork.
- The classic greedy strategies (`DSATUR`, `largest_first`, ...) remain
  available for speed comparisons and reproducing older results.
- `force_k` targets a fixed layer count and accepts conflicts; use only when
  the layer count is mandated by production constraints.

## Practical Recommendations

1. Start with `Balanced + minimum_layers`.
2. Run `Estimate Complexity`.
3. If complexity is high:
   - try `Performance Mode`, or
   - switch to `Flat Complexity` if strict non-overlap is required.
4. For final production output:
   - use `Accurate` preset
   - choose `Illustrator-safe` or `Print` profile.
