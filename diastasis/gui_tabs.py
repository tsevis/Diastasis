"""
Mode-tab builders for the Diastasis GUI. Each function populates one
notebook tab with its controls, kept out of gui.py for cohesion.
"""
import tkinter as tk
from tkinter import ttk

from .graph_solver import GraphSolver

OVERLAID_ALGO_GUIDE = {
    "minimum_layers": "Best. Tries several strategies, refines, and proves optimality when possible.",
    "largest_first": "(Welsh-Powell) Fast. Colors nodes with the most neighbors first.",
    "DSATUR": "Good balance of speed and quality. Prioritizes high saturation nodes.",
    "independent_set": "Potentially high quality. Finds non-overlapping groups first.",
    "smallest_last": "Good quality. Colors in reverse simplification order.",
    "random_sequential": "Fastest, but least optimal.",
    "connected_sequential_bfs": "Breadth-first traversal coloring.",
    "connected_sequential_dfs": "Depth-first traversal coloring.",
    "force_k": "Forces a specific number of layers minimizing overlap.",
}


def build_overlaid_tab(app):
    algo_frame = ttk.Frame(app.overlaid_tab)
    algo_frame.pack(fill=tk.X, pady=8, padx=4)

    ttk.Label(algo_frame, text="Algorithm:").pack(side=tk.LEFT, padx=(0, 8))
    app.algo_combobox = ttk.Combobox(
        algo_frame, textvariable=app.algorithm,
        values=GraphSolver.AVAILABLE_ALGORITHMS, state="readonly", width=28,
    )
    app.algo_combobox.pack(side=tk.LEFT)
    app.algo_combobox.bind("<<ComboboxSelected>>", lambda _evt: app.on_algo_change())

    app.num_layers_frame = ttk.Frame(app.overlaid_tab)
    ttk.Label(app.num_layers_frame, text="Number of Layers:").pack(side=tk.LEFT, padx=(0, 8))
    app.num_layers_entry = ttk.Entry(app.num_layers_frame, textvariable=app.num_layers, width=6)
    app.num_layers_entry.pack(side=tk.LEFT)

    optimizer_frame = ttk.Frame(app.overlaid_tab)
    optimizer_frame.pack(fill=tk.X, padx=4, pady=(0, 8))
    app.optimizer_check = ttk.Checkbutton(
        optimizer_frame, text="Apply post-processing optimization (slower)",
        variable=app.use_optimizer,
    )
    app.optimizer_check.pack(anchor=tk.W)

    explanation_frame = ttk.LabelFrame(app.overlaid_tab, text="Algorithm Guide")
    explanation_frame.pack(fill=tk.X, padx=4, pady=(0, 6))
    for algo, explanation in OVERLAID_ALGO_GUIDE.items():
        ttk.Label(
            explanation_frame, text=f"- {algo}: {explanation}", wraplength=410, justify=tk.LEFT
        ).pack(anchor=tk.W, padx=6, pady=1)


def build_flat_tab(app):
    algo_frame = ttk.Frame(app.flat_tab)
    algo_frame.pack(fill=tk.X, pady=8, padx=4)

    ttk.Label(algo_frame, text="Flat Algorithm:").pack(side=tk.LEFT, padx=(0, 8))
    app.flat_algo_combobox = ttk.Combobox(
        algo_frame, textvariable=app.flat_algorithm,
        values=GraphSolver.AVAILABLE_ALGORITHMS, state="readonly", width=24,
    )
    app.flat_algo_combobox.pack(side=tk.LEFT)
    app.flat_algo_combobox.bind("<<ComboboxSelected>>", lambda _evt: app.on_flat_algo_change())

    app.flat_num_layers_frame = ttk.Frame(app.flat_tab)
    ttk.Label(app.flat_num_layers_frame, text="Flat Number of Layers:").pack(side=tk.LEFT, padx=(0, 8))
    app.flat_num_layers_entry = ttk.Entry(app.flat_num_layers_frame, textvariable=app.flat_num_layers, width=6)
    app.flat_num_layers_entry.pack(side=tk.LEFT)

    policy_frame = ttk.Frame(app.flat_tab)
    policy_frame.pack(fill=tk.X, pady=(0, 8), padx=4)
    ttk.Label(policy_frame, text="Touch Policy:").pack(side=tk.LEFT, padx=(0, 8))
    app.flat_policy_combobox = ttk.Combobox(
        policy_frame, textvariable=app.flat_touch_policy,
        values=["No edge/corner touching", "Allow corner touching"], state="readonly", width=24,
    )
    app.flat_policy_combobox.pack(side=tk.LEFT)

    priority_frame = ttk.Frame(app.flat_tab)
    priority_frame.pack(fill=tk.X, pady=(0, 8), padx=4)
    ttk.Label(priority_frame, text="Overlap Priority:").pack(side=tk.LEFT, padx=(0, 8))
    app.flat_priority_combobox = ttk.Combobox(
        priority_frame, textvariable=app.flat_priority_order,
        values=["Source order", "Largest first", "Smallest first"], state="readonly", width=24,
    )
    app.flat_priority_combobox.pack(side=tk.LEFT)

    sliver_frame = ttk.Frame(app.flat_tab)
    sliver_frame.pack(fill=tk.X, pady=(0, 8), padx=4)
    ttk.Label(sliver_frame, text="Drop slivers below (canvas ratio):").pack(side=tk.LEFT, padx=(0, 8))
    ttk.Entry(sliver_frame, textvariable=app.flat_min_fragment, width=8).pack(side=tk.LEFT)

    info_frame = ttk.LabelFrame(app.flat_tab, text="Flat Complexity Behavior")
    info_frame.pack(fill=tk.X, padx=4, pady=(0, 6))
    ttk.Label(
        info_frame,
        text=(
            "No edge/corner touching: any contact forces different layers.\n"
            "Allow corner touching: point-only corner contacts may share layers.\n"
            "Overlap priority controls which shapes keep contested areas.\n"
            "Drop slivers removes sub-visible fragments left by flattening (0 = keep all).\n"
            "Use force_k only when you intentionally accept less strict separation."
        ),
        wraplength=410, justify=tk.LEFT,
    ).pack(anchor=tk.W, padx=6, pady=6)

    app.on_flat_algo_change()


def build_color_tab(app):
    tolerance_frame = ttk.Frame(app.color_tab)
    tolerance_frame.pack(fill=tk.X, pady=8, padx=4)
    ttk.Label(tolerance_frame, text="Merge tolerance (RGB distance):").pack(side=tk.LEFT, padx=(0, 8))
    ttk.Entry(tolerance_frame, textvariable=app.color_tolerance, width=8).pack(side=tk.LEFT)

    unify_frame = ttk.Frame(app.color_tab)
    unify_frame.pack(fill=tk.X, pady=(0, 8), padx=4)
    ttk.Checkbutton(
        unify_frame, text="Unify plate colors to representative ink",
        variable=app.unify_plate_colors,
    ).pack(anchor=tk.W)

    info_frame = ttk.LabelFrame(app.color_tab, text="Color Separation Behavior")
    info_frame.pack(fill=tk.X, padx=4, pady=(0, 6))
    ttk.Label(
        info_frame,
        text=(
            "One plate per fill color — the screen-print / vinyl / risograph model.\n"
            "Merge tolerance groups near-identical inks onto one plate to cut plate\n"
            "count (0 = exact match only). Unify repaints each shape with its plate's\n"
            "representative ink for true single-ink plates. Shapes with no fill are\n"
            "collected onto one plate."
        ),
        wraplength=410, justify=tk.LEFT,
    ).pack(anchor=tk.W, padx=6, pady=6)
