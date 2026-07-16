"""
Diastasis: separate complex SVG artwork into production-ready layers
via graph coloring, using the fewest layers possible.
"""
from .main import run_diastasis
from .svg_export import (
    save_layers_to_files,
    save_layers_to_separate_files,
    save_single_layer_file,
)

__version__ = "0.4.0"

__all__ = [
    "run_diastasis",
    "save_layers_to_files",
    "save_layers_to_separate_files",
    "save_single_layer_file",
    "__version__",
]
