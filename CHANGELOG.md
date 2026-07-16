# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New default coloring algorithm `minimum_layers`: runs a portfolio of greedy
  strategies (with Kempe-chain interchange), iterated-greedy refinement, and an
  exact branch-and-bound pass on small graphs. Stops early when the proven
  lower bound is reached, so results are frequently provably optimal.
- Proven lower bound ("minimum proven required layers") now reported for both
  modes, with a "Layer count is provably optimal" note when it is met.
- SVG `transform` support (matrix, translate, scale, rotate, skewX, skewY),
  including inherited group transforms.
- Compound `<path>` support: multiple subpaths are combined according to the
  element's `fill-rule` (winding-aware `nonzero` by default, `evenodd` when
  specified), so holes and disjoint contours produce correct geometry.
- Curved path segments (Bezier/arc) are now sampled instead of collapsed to
  their endpoints, giving accurate overlap detection for curved artwork.
- Headless CLI (`cli.py`): single-file and batch processing, complexity
  estimates, and all pipeline options without the GUI.
- Per-layer file export (`save_layers_to_separate_files`): one registered
  SVG per layer with shared canvas and crop marks.
- High-fidelity export module (`svg_export.py`): untransformed basic shapes
  re-emit their original native markup instead of polygonized paths.
- `polyline` support, `defs`/`symbol`/`clipPath`/`mask` content excluded
  from direct rendering, and `use` references resolved with correct
  transform composition.
- Canvas size now follows the `viewBox` coordinate system, fixing wrong
  output scale for files sized in physical units (e.g. mm).
- Vectorized overlap/contact detection (shapely 2 bulk STRtree): contacts
  about 10x faster, overlaps about 2.5x faster at 3000 shapes.

### Changed
- Layer lower bound now uses exact max-clique branch and bound instead of the
  slow Ramsey approximation (about 1000x faster on typical conflict graphs,
  and tighter).
- Flat flattening and visibility clipping subtract only spatially local
  geometry instead of one giant accumulated union (about 40x faster at
  1000+ shapes, identical output).
- Generated paths now carry `fill-rule="evenodd"` so holes render correctly.
- Removed empty placeholder modules `utils.py` and `performance_optimizer.py`.

### Fixed
- Overlaid mode no longer wastes an extra layer when the largest (background)
  shape already occupies a layer of its own.
- `optimize_coloring` previously could only remove single-shape layers; it now
  performs a real iterated-greedy reduction that never increases layer count.
- Paths with transforms no longer export stale untransformed path data.

## [0.2.0] - 2026-02-20

### Added
- Dual processing modes in GUI: `Overlaid Complexity` and `Flat Complexity`.
- Flat-mode controls:
  - Touch policy (`No edge/corner touching`, `Allow corner touching`)
  - Overlap priority (`Source order`, `Largest first`, `Smallest first`)
- Optional clipping to visible boundaries (`Clip Shapes To Visible Boundaries`).
- Single-layer clipped export (`Save Clipped 1-Layer As...`).
- Preservation of original fill colors for clipped outputs.
- Performance mode toggle for weaker systems / very large files.
- Quality presets (`Accurate`, `Balanced`, `Fast`).
- Complexity estimation with shape count, candidate pairs, density, and ETA.
- Batch folder processing for SVG files using current settings.
- Export profiles (`Illustrator-safe`, `Print`, `Web`).
- Layer analytics in processing summary:
  - overlap/conflict metrics
  - tiny fragment count
  - per-layer area share
- `CHANGELOG.md` added.

### Changed
- Refactored GUI to share one input/preview workflow across both tabs.
- Improved dark-mode preview behavior (canvas now updates correctly on macOS).
- Increased left-panel width and improved multiline complexity report readability.
- Improved geometry handling for large files and robust shape sanitization paths.

### Fixed
- Multiple flat/overlaid processing regressions around shape separation and layer assignment.
- `force_k` stability and error handling paths.
- `NameError` in threaded GUI error callback.
- Topology exception handling in clipping/difference operations via safer geometry ops.
- MultiPolygon/GeometryCollection export path handling.

### Tests
- Expanded tests for:
  - geometry overlap/contact detection
  - flat behavior and policy handling
  - complexity estimation
  - export profile behavior
  - performance mode summaries
