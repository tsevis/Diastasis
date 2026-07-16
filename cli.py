"""
Headless command-line interface for Diastasis.

Examples:
    python cli.py artwork.svg -o output/
    python cli.py artwork.svg -o output/ --mode flat --separate-files
    python cli.py --batch input_folder/ -o output/ --profile Print
"""
import argparse
import os
import sys
from typing import List, Optional

from graph_solver import GraphSolver
from main import estimate_processing_complexity, run_diastasis
from svg_export import (
    EXPORT_PROFILES,
    save_layers_to_files,
    save_layers_to_separate_files,
)

TOUCH_POLICIES = {"strict": "any_touch", "corners": "edge_or_overlap"}
PRIORITY_ORDERS = ("source", "largest_first", "smallest_first")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diastasis",
        description="Separate SVG artwork into production-ready layers (fewest layers possible).",
    )
    parser.add_argument("input", nargs="?", help="Input SVG file (omit when using --batch).")
    parser.add_argument("--batch", metavar="FOLDER", help="Process every .svg file in FOLDER.")
    parser.add_argument("-o", "--output", default="output", help="Output directory (default: output).")
    parser.add_argument(
        "--mode", choices=("overlaid", "flat"), default="overlaid",
        help="overlaid: overlap-aware layering. flat: strict area-exclusive separation.",
    )
    parser.add_argument(
        "--algorithm", choices=GraphSolver.AVAILABLE_ALGORITHMS, default="minimum_layers",
        help="Coloring algorithm for the active mode (default: minimum_layers).",
    )
    parser.add_argument(
        "--num-layers", type=int, default=None,
        help="Target layer count, required by the force_k algorithm.",
    )
    parser.add_argument(
        "--touch-policy", choices=sorted(TOUCH_POLICIES), default="strict",
        help="flat mode: strict = any contact conflicts; corners = corner-only touches may share a layer.",
    )
    parser.add_argument(
        "--priority", choices=PRIORITY_ORDERS, default="source",
        help="flat mode: which shape keeps contested area (default: source order).",
    )
    parser.add_argument("--clip", action="store_true", help="Clip shapes to visible boundaries first.")
    parser.add_argument("--performance", action="store_true", help="Simplify geometry on very large files.")
    parser.add_argument(
        "--profile", choices=sorted(EXPORT_PROFILES), default="Illustrator-safe",
        help="Export profile (default: Illustrator-safe).",
    )
    parser.add_argument(
        "--recolor", action="store_true",
        help="Fill each layer with a distinct color instead of preserving original fills.",
    )
    parser.add_argument(
        "--separate-files", action="store_true",
        help="Also write one registered SVG file per layer.",
    )
    parser.add_argument("--estimate", action="store_true", help="Print a complexity estimate and exit.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress the per-file summary.")
    return parser


def _process_file(svg_path: str, args: argparse.Namespace) -> bool:
    """Process one SVG file. Returns True on success."""
    name = os.path.splitext(os.path.basename(svg_path))[0]

    result = run_diastasis(
        svg_path,
        algorithm=args.algorithm,
        num_layers=args.num_layers,
        mode=args.mode,
        flat_algorithm=args.algorithm,
        flat_num_layers=args.num_layers,
        flat_touch_policy=TOUCH_POLICIES[args.touch_policy],
        flat_priority_order=args.priority,
        clip_visible_boundaries=args.clip,
        performance_mode=args.performance,
    )
    if result[0] is None:
        print(f"error: {svg_path}: {result[2]}", file=sys.stderr)
        return False

    shapes, grouped_coloring, summary, width, height = result
    save_layers_to_files(
        shapes, grouped_coloring, args.output, name, width, height,
        preserve_original_colors=not args.recolor,
        export_profile=args.profile,
    )
    if args.separate_files:
        save_layers_to_separate_files(
            shapes, grouped_coloring, args.output, name, width, height,
            preserve_original_colors=not args.recolor,
            export_profile=args.profile,
        )
    if not args.quiet:
        print(f"--- {os.path.basename(svg_path)} ---")
        print(summary)
    return True


def _batch_inputs(folder: str) -> List[str]:
    return sorted(
        os.path.join(folder, entry)
        for entry in os.listdir(folder)
        if entry.lower().endswith(".svg")
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if bool(args.input) == bool(args.batch):
        print("error: provide exactly one of an input file or --batch FOLDER", file=sys.stderr)
        return 2
    if args.algorithm == "force_k" and (args.num_layers is None or args.num_layers <= 0):
        print("error: --num-layers is required (and must be positive) with force_k", file=sys.stderr)
        return 2

    if args.estimate:
        targets = [args.input] if args.input else _batch_inputs(args.batch)
        for svg_path in targets:
            estimate = estimate_processing_complexity(svg_path)
            print(
                f"{os.path.basename(svg_path)}: {estimate['shape_count']} shapes, "
                f"{estimate['candidate_pairs']} candidate pairs, "
                f"complexity {estimate['complexity_label']}, "
                f"~{estimate['eta_seconds']:.1f}s"
            )
        return 0

    if args.input:
        if not os.path.isfile(args.input):
            print(f"error: input file not found: {args.input}", file=sys.stderr)
            return 2
        return 0 if _process_file(args.input, args) else 1

    if not os.path.isdir(args.batch):
        print(f"error: batch folder not found: {args.batch}", file=sys.stderr)
        return 2
    targets = _batch_inputs(args.batch)
    if not targets:
        print(f"error: no .svg files in {args.batch}", file=sys.stderr)
        return 1

    failures = sum(0 if _process_file(svg_path, args) else 1 for svg_path in targets)
    print(f"Processed {len(targets) - failures}/{len(targets)} files into {args.output}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
