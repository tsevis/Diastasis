# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Placeholder for upcoming changes.

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
