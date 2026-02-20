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
  - Enables optimizer.
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

## Export Controls

## Save Layers As...

Creates a multi-layer SVG from processing result.

## Save Clipped 1-Layer As...

Creates one flattened clipped SVG layer.

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

## Practical Recommendations

1. Start with `Balanced + DSATUR`.
2. Run `Estimate Complexity`.
3. If complexity is high:
   - try `Performance Mode`, or
   - switch to `Flat Complexity` if strict non-overlap is required.
4. For final production output:
   - use `Accurate` preset
   - choose `Illustrator-safe` or `Print` profile.
