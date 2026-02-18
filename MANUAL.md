# Diastasis Manual

## Why these functions/options exist

Diastasis has many controls because different SVG workflows need different constraints:

- Some jobs need strict separation with zero shared area between shapes/layers.
- Some jobs must keep visual stacking and only export what is actually visible.
- Some jobs need fewer layers even if small conflicts are allowed.
- Some jobs prioritize preserving major blocks; others preserve detail fragments.

This manual explains when to use each option.

## Core modes

## 1. Overlaid Complexity

Use when you want classic overlap-aware layer assignment from original shapes.

Best for:
- General layer separation
- Quick processing
- Traditional graph-coloring approach

Main controls:
- `Algorithm`
- `Apply post-processing optimization`
- `force_k` + `Number of Layers`

## 2. Flat Complexity

Use when you need area-exclusive results and strict geometric control.

Best for:
- Manufacturing workflows
- No shared area between resulting shape fragments
- Controlling touching rules and overlap ownership

Main controls:
- `Flat Algorithm`
- `Touch Policy`
- `Overlap Priority`
- `force_k` + `Flat Number of Layers`

## Global option

## Clip Shapes To Visible Boundaries

What it does:
- Removes hidden/occluded regions based on SVG stacking (top shapes hide lower shapes).
- Keeps only what is actually visible in the source artwork.

Use when:
- Source SVG has many stacked overlays
- You want exported geometry to match visual result exactly

Also:
- Clipped exports preserve original shape fill colors.

## Flat controls in detail

## Touch Policy

### No edge/corner touching
- Any contact is conflict.
- Strictest separation.

### Allow corner touching
- Point-only corner contacts are allowed.
- Useful for grid-like designs where corner touches are acceptable.

## Overlap Priority

Determines which shapes keep contested overlapping regions during flattening.

### Source order
- Follows SVG visual stack (top-most keeps area).
- Best default for fidelity to the artwork.

### Largest first
- Preserves large regions first.
- Good for broad structural blocks.

### Smallest first
- Preserves detail/small regions first.
- Good for fine-detail mosaics.

## Algorithms and when to use them

## DSATUR (recommended default)
- Good quality/speed balance.
- Usually strong first choice for both modes.

## largest_first / smallest_last / independent_set
- Alternative heuristics with different tradeoffs.
- Useful when DSATUR result needs variation.

## connected_sequential_bfs / connected_sequential_dfs
- Traversal-based heuristics.
- Can produce different layer structures on connected graphs.

## random_sequential
- Fast and simple baseline.

## force_k
- Forces target layer count `k`.
- In Flat mode: soft-constrained, may introduce conflicts if `k` is too low.
- Summary reports lower bound and conflict count.

Use when:
- You must cap layer count for production constraints.

## Exports

## Save Layers As...
- Writes multi-layer SVG.
- Each layer corresponds to color/group assignment.

## Save Clipped 1-Layer As...
- Writes one single SVG layer from processed shapes.
- Ideal when you need one flattened clipped output.

## Heavy files: practical guidance

If processing is slow:
1. Start with `Overlaid Complexity + DSATUR`.
2. Enable clipping only when needed.
3. In Flat mode, prefer `DSATUR` before trying exotic algorithms.
4. Use `force_k` only when layer count must be capped.
5. If `force_k` causes high conflicts, increase `k` or relax touch policy.

## Typical recipes

## Recipe A: strict manufacturing separation
- Mode: Flat
- Clip: ON
- Touch Policy: No edge/corner touching
- Overlap Priority: Source order
- Algorithm: DSATUR

## Recipe B: preserve tiny details
- Mode: Flat
- Clip: ON
- Overlap Priority: Smallest first
- Algorithm: DSATUR

## Recipe C: minimum layers with accepted compromises
- Mode: Flat
- Clip: ON or OFF (depends on source)
- Algorithm: force_k
- Start with `k` near summary lower bound and adjust.

## Troubleshooting

## "maximum recursion depth exceeded"
- Diastasis now falls back safely to DSATUR when recursion-heavy strategies fail.
- Retry with DSATUR directly for stability.

## "Processing..." seems stuck on huge files
- Wait for completion once, then try DSATUR + Overlaid baseline.
- Use Flat mode only when strict area logic is required.

## Color mismatch after clipping
- Ensure clipping is enabled before processing.
- Use current build: clipped exports preserve original fills.
