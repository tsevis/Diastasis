import random
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np

from .svg_parser import Shape


class _ExactSearchBudgetExhausted(Exception):
    """Raised internally when the exact solver runs out of its step budget."""


class GraphSolver:
    # A list of all available coloring strategies
    AVAILABLE_ALGORITHMS = [
        "minimum_layers",
        "largest_first",
        "smallest_last",
        "independent_set",
        "DSATUR",
        "random_sequential",
        "connected_sequential_bfs",
        "connected_sequential_dfs",
        "force_k"
    ]

    # Graphs above these sizes skip the more expensive portfolio members.
    LARGE_GRAPH_NODES = 2000
    LARGE_GRAPH_EDGES = 100_000
    # Above these sizes, minimum_layers falls back to a single DSATUR pass.
    HUGE_GRAPH_NODES = 20_000
    HUGE_GRAPH_EDGES = 500_000
    # Exact search is only attempted on graphs small enough to finish quickly.
    EXACT_NODE_LIMIT = 70
    EXACT_STEP_BUDGET = 200_000

    def build_overlap_graph(self, shapes: List[Shape], overlaps: List[Tuple[int, int, float]]) -> nx.Graph:
        """Builds a graph where nodes are shapes and edges represent overlaps with weights."""
        graph = nx.Graph()
        for i in range(len(shapes)):
            graph.add_node(i, size=shapes[i].geometry.area) # Add node size for sorting

        for i, j, overlap_area in overlaps:
            graph.add_edge(i, j, weight=overlap_area)

        return graph

    def solve_coloring(
        self, graph: nx.Graph, algorithm: str = "minimum_layers", use_optimizer: bool = False, num_layers: int = None
    ) -> Dict[int, int]:
        """
        Colors the graph using the specified algorithm.
        The color represents the layer number.

        Args:
            graph: The NetworkX graph to color.
            algorithm: The coloring strategy to use.
            use_optimizer: If True, applies a local search optimization.
            num_layers: The target number of layers for 'force_k' algorithm.

        Returns:
            A dictionary mapping node IDs to their assigned color (layer).
        """
        if algorithm not in self.AVAILABLE_ALGORITHMS:
            raise ValueError(
                f"Unknown coloring algorithm: {algorithm}. "
                f"Available options are: {self.AVAILABLE_ALGORITHMS}"
            )

        if algorithm == "force_k":
            if num_layers is None or num_layers <= 0:
                raise ValueError("A positive number of layers must be provided for 'force_k' algorithm.")
            return self.force_k_coloring(graph, num_layers)

        if algorithm == "minimum_layers":
            # Refinement is built in, so use_optimizer adds nothing here.
            return self.solve_minimum_coloring(graph)

        # Use the highly optimized greedy_color function from NetworkX.
        # Some strategies (notably deep DFS traversals) may hit Python recursion
        # limits on very large/complex graphs; fallback to DSATUR for robustness.
        try:
            coloring = nx.greedy_color(graph, strategy=algorithm)
        except RecursionError:
            if algorithm != "DSATUR":
                coloring = nx.greedy_color(graph, strategy="DSATUR")
            else:
                raise

        if use_optimizer:
            coloring = self.optimize_coloring(graph, coloring)

        return coloring

    def solve_minimum_coloring(self, graph: nx.Graph) -> Dict[int, int]:
        """
        Best-effort minimum coloring: portfolio of greedy strategies with
        interchange, iterated-greedy refinement, and an exact branch-and-bound
        pass on small graphs. Stops as soon as a proven lower bound is met.
        """
        if graph.number_of_nodes() == 0:
            return {}
        if graph.number_of_edges() == 0:
            return {node: 0 for node in graph.nodes()}

        if (
            graph.number_of_nodes() > self.HUGE_GRAPH_NODES
            or graph.number_of_edges() > self.HUGE_GRAPH_EDGES
        ):
            return self._normalize_colors(nx.greedy_color(graph, strategy="DSATUR"))

        is_large = (
            graph.number_of_nodes() > self.LARGE_GRAPH_NODES
            or graph.number_of_edges() > self.LARGE_GRAPH_EDGES
        )

        lower_bound = self.clique_lower_bound(graph)
        best = self._portfolio_coloring(graph, lower_bound)

        if self.get_num_layers(best) > lower_bound:
            best = self._iterated_greedy_refine(
                graph,
                best,
                lower_bound,
                max_iterations=12 if is_large else 60,
                stall_limit=6 if is_large else 15,
            )

        if (
            self.get_num_layers(best) > lower_bound
            and graph.number_of_nodes() <= self.EXACT_NODE_LIMIT
        ):
            best = self._exact_branch_and_bound(graph, best, lower_bound)

        return self._normalize_colors(best)

    def clique_lower_bound(self, graph: nx.Graph) -> int:
        """
        Return a proven lower bound on the chromatic number (clique size).
        """
        if graph.number_of_nodes() == 0:
            return 0
        if graph.number_of_edges() == 0:
            return 1

        lower_bound = max(2, self._greedy_clique_size(graph))

        # Exact max clique via branch and bound; sparse geometric conflict
        # graphs solve in milliseconds-to-seconds, and a tight bound lets the
        # portfolio certify optimality early, so gate only on extreme sizes.
        if graph.number_of_nodes() <= 12_000 and graph.number_of_edges() <= 200_000:
            try:
                clique_nodes, _ = nx.max_weight_clique(graph, weight=None)
                lower_bound = max(lower_bound, len(clique_nodes))
            except Exception:
                pass

        return lower_bound

    def _greedy_clique_size(self, graph: nx.Graph, num_seeds: int = 5) -> int:
        """
        Cheap greedy clique heuristic: grow a clique from each of the
        highest-degree nodes and keep the best size found.
        """
        seeds = sorted(graph.nodes(), key=lambda n: graph.degree(n), reverse=True)[:num_seeds]
        best_size = 1
        for seed in seeds:
            clique_members = {seed}
            candidates = set(graph.neighbors(seed))
            while candidates:
                node = max(candidates, key=lambda n: graph.degree(n))
                clique_members.add(node)
                candidates &= set(graph.neighbors(node))
            best_size = max(best_size, len(clique_members))
        return best_size

    def _portfolio_coloring(self, graph: nx.Graph, lower_bound: int) -> Dict[int, int]:
        """
        Run several greedy strategies (with Kempe-chain interchange where
        supported) and keep the coloring with the fewest colors.
        """
        is_large = (
            graph.number_of_nodes() > self.LARGE_GRAPH_NODES
            or graph.number_of_edges() > self.LARGE_GRAPH_EDGES
        )

        best: Optional[Dict[int, int]] = None
        for coloring in self._portfolio_candidates(graph, is_large):
            if best is None or self.get_num_layers(coloring) < self.get_num_layers(best):
                best = coloring
            if self.get_num_layers(best) <= lower_bound:
                break
        return best

    def _portfolio_candidates(self, graph: nx.Graph, is_large: bool):
        # On large graphs run the near-linear strategies first: with a tight
        # lower bound they often certify optimality before the O(n^2) DSATUR
        # pass is ever needed.
        if not is_large:
            yield nx.greedy_color(graph, strategy="DSATUR")

        interchange = not is_large
        for strategy in ("largest_first", "smallest_last", "connected_sequential_bfs"):
            try:
                yield nx.greedy_color(graph, strategy=strategy, interchange=interchange)
            except (RecursionError, nx.NetworkXPointlessConcept):
                continue

        num_random_orders = 2 if is_large else 6
        nodes = list(graph.nodes())
        for seed in range(num_random_orders):
            order = list(nodes)
            random.Random(seed).shuffle(order)
            yield self._greedy_from_order(graph, order)

        if is_large:
            yield nx.greedy_color(graph, strategy="DSATUR")

    def _greedy_from_order(self, graph: nx.Graph, order: List[int]) -> Dict[int, int]:
        """Greedy coloring that assigns each node the lowest color not used by neighbors."""
        coloring: Dict[int, int] = {}
        for node in order:
            neighbor_colors = {coloring[nbr] for nbr in graph.neighbors(node) if nbr in coloring}
            color = 0
            while color in neighbor_colors:
                color += 1
            coloring[node] = color
        return coloring

    def _iterated_greedy_refine(
        self,
        graph: nx.Graph,
        coloring: Dict[int, int],
        lower_bound: int,
        max_iterations: int = 60,
        stall_limit: int = 15,
    ) -> Dict[int, int]:
        """
        Iterated greedy (Culberson): re-run greedy on nodes ordered by whole
        color classes. This never increases the color count and often lowers it.
        """
        rng = random.Random(1)
        best = dict(coloring)
        current = dict(coloring)
        stalled = 0

        for iteration in range(max_iterations):
            classes: Dict[int, List[int]] = defaultdict(list)
            for node, color in current.items():
                classes[color].append(node)
            class_list = list(classes.values())

            mode = iteration % 4
            if mode == 0:
                class_list.sort(key=len, reverse=True)
            elif mode == 1:
                class_list.sort(key=len)
            elif mode == 2:
                rng.shuffle(class_list)
            else:
                class_list.reverse()

            order = [node for color_class in class_list for node in color_class]
            current = self._greedy_from_order(graph, order)

            if self.get_num_layers(current) < self.get_num_layers(best):
                best = dict(current)
                stalled = 0
                if self.get_num_layers(best) <= lower_bound:
                    break
            else:
                stalled += 1
                if stalled >= stall_limit:
                    break

        return best

    def _exact_branch_and_bound(
        self,
        graph: nx.Graph,
        best_coloring: Dict[int, int],
        lower_bound: int,
    ) -> Dict[int, int]:
        """
        DSATUR-based branch and bound. Proves optimality when it completes
        within its step budget; otherwise returns the best coloring found.
        """
        best = dict(best_coloring)
        best_count = self.get_num_layers(best)
        if best_count <= lower_bound:
            return best

        nodes = list(graph.nodes())
        adjacency: Dict[int, Set[int]] = {node: set(graph.neighbors(node)) for node in nodes}
        assignment: Dict[int, int] = {}
        neighbor_colors: Dict[int, Set[int]] = {node: set() for node in nodes}
        steps = 0

        def pick_node() -> int:
            unassigned = [node for node in nodes if node not in assignment]
            return max(unassigned, key=lambda n: (len(neighbor_colors[n]), len(adjacency[n])))

        def search(used_colors: int) -> None:
            nonlocal best, best_count, steps
            steps += 1
            if steps > self.EXACT_STEP_BUDGET:
                raise _ExactSearchBudgetExhausted()

            if len(assignment) == len(nodes):
                best = dict(assignment)
                best_count = used_colors
                return

            node = pick_node()
            for color in range(used_colors + 1):
                # best_count can tighten during recursion, so re-check each turn.
                if color >= best_count - 1:
                    break
                if color in neighbor_colors[node]:
                    continue
                assignment[node] = color
                touched = [nbr for nbr in adjacency[node] if color not in neighbor_colors[nbr]]
                for nbr in touched:
                    neighbor_colors[nbr].add(color)

                search(max(used_colors, color + 1))

                for nbr in touched:
                    neighbor_colors[nbr].discard(color)
                del assignment[node]

                if best_count <= lower_bound:
                    return

        try:
            search(0)
        except (_ExactSearchBudgetExhausted, RecursionError):
            pass

        return best

    def _normalize_colors(self, coloring: Dict[int, int]) -> Dict[int, int]:
        """Renumber colors to a contiguous 0..k-1 range, largest class first."""
        class_sizes: Dict[int, int] = defaultdict(int)
        for color in coloring.values():
            class_sizes[color] += 1
        remap = {
            old_color: new_color
            for new_color, old_color in enumerate(
                sorted(class_sizes, key=lambda c: (-class_sizes[c], c))
            )
        }
        return {node: remap[color] for node, color in coloring.items()}

    def force_k_coloring(self, graph: nx.Graph, k: int) -> Dict[int, int]:
        """
        Assigns each node to one of k layers to minimize overlap.
        Uses a greedy approach based on minimizing the cost of adding a node to a layer.

        Args:
            graph: A weighted NetworkX graph.
            k: The desired number of layers.

        Returns:
            A dictionary mapping node IDs to their assigned layer.
        """
        coloring = {}
        layers = [[] for _ in range(k)]

        # Sort nodes by size (area) in descending order as a heuristic
        sorted_nodes = sorted(graph.nodes(data=True), key=lambda x: x[1].get('size', 0), reverse=True)

        for node, _ in sorted_nodes:
            costs = np.zeros(k)
            for i in range(k):
                cost = 0
                for neighbor in graph.neighbors(node):
                    if neighbor in layers[i]:
                        cost += graph[node][neighbor]['weight']
                costs[i] = cost

            # Assign node to the layer with the minimum cost
            best_layer = np.argmin(costs)
            layers[best_layer].append(node)
            coloring[node] = best_layer

        return coloring

    def optimize_coloring(
        self, graph: nx.Graph, initial_coloring: Dict[int, int], max_iterations: int = 100
    ) -> Dict[int, int]:
        """
        Reduce the number of colors of a valid coloring via iterated greedy.
        Never increases the color count and keeps the coloring valid.
        """
        if not initial_coloring:
            return dict(initial_coloring)

        refined = self._iterated_greedy_refine(
            graph, initial_coloring, lower_bound=1, max_iterations=max_iterations
        )
        return self._normalize_colors(refined)

    def _is_color_valid(self, graph: nx.Graph, node: int, color: int, coloring: Dict[int, int]) -> bool:
        """Checks if a given color is valid for a node."""
        for neighbor in graph.neighbors(node):
            if neighbor in coloring and coloring[neighbor] == color:
                return False
        return True

    def get_num_layers(self, coloring: Dict[int, int]) -> int:
        """Calculates the number of layers from a coloring dictionary."""
        if not coloring:
            return 0
        return len(set(coloring.values()))
