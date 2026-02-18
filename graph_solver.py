from typing import List, Tuple, Dict
import networkx as nx
from svg_parser import Shape
import numpy as np

class GraphSolver:
    # A list of all available coloring strategies
    AVAILABLE_ALGORITHMS = [
        "largest_first",
        "smallest_last",
        "independent_set",
        "DSATUR",
        "random_sequential",
        "connected_sequential_bfs",
        "connected_sequential_dfs",
        "force_k"
    ]

    def build_overlap_graph(self, shapes: List[Shape], overlaps: List[Tuple[int, int, float]]) -> nx.Graph:
        """Builds a graph where nodes are shapes and edges represent overlaps with weights."""
        graph = nx.Graph()
        for i in range(len(shapes)):
            graph.add_node(i, size=shapes[i].geometry.area) # Add node size for sorting
        
        for i, j, overlap_area in overlaps:
            graph.add_edge(i, j, weight=overlap_area)
            
        return graph

    def solve_coloring(
        self, graph: nx.Graph, algorithm: str = "largest_first", use_optimizer: bool = False, num_layers: int = None
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
        Applies a local search optimization to potentially reduce the number of colors.
        """
        current_coloring = initial_coloring.copy()
        
        for _ in range(max_iterations):
            num_colors = len(set(current_coloring.values()))
            improved_in_pass = False
            
            for node in sorted(graph.nodes()):
                for new_color in range(num_colors):
                    if self._is_color_valid(graph, node, new_color, current_coloring):
                        original_color = current_coloring[node]
                        if original_color == new_color:
                            continue

                        is_original_color_freeable = all(
                            current_coloring[n] != original_color
                            for n in graph.nodes() if n != node
                        )

                        if is_original_color_freeable:
                            current_coloring[node] = new_color
                            for n, c in current_coloring.items():
                                if c > original_color:
                                    current_coloring[n] = c - 1
                            improved_in_pass = True
                            break
                
                if improved_in_pass:
                    break
            
            if not improved_in_pass:
                break
                
        return current_coloring

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
        return max(coloring.values()) + 1
