import pytest
import networkx as nx
from graph_solver import GraphSolver
from svg_parser import Shape
from shapely.geometry import box
 # Assuming Shape class is available

# Fixture for creating simple shapes (needed for build_overlap_graph)
@pytest.fixture
def simple_shapes():
    # These shapes need actual geometry for graph_solver tests
    return [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(5, 5, 15, 15), metadata={}),
        Shape(id=2, geometry=box(20, 20, 30, 30), metadata={}),
        Shape(id=3, geometry=box(0, 20, 10, 30), metadata={}),
        Shape(id=4, geometry=box(5, 25, 15, 35), metadata={})
    ]

def test_build_overlap_graph(simple_shapes):
    solver = GraphSolver()
    overlaps = [(0, 1, 25.0), (3, 4, 25.0)]
    graph = solver.build_overlap_graph(simple_shapes, overlaps)
    
    assert isinstance(graph, nx.Graph)
    assert len(graph.nodes()) == 5
    assert len(graph.edges()) == 2
    assert graph.has_edge(0, 1)
    assert graph[0][1]['weight'] == 25.0
    assert graph.has_edge(3, 4)
    assert graph[3][4]['weight'] == 25.0
    assert not graph.has_edge(0, 2)



def test_solve_coloring_algorithm_choice():
    solver = GraphSolver()
    graph = nx.Graph()
    graph.add_edges_from([(0, 1), (0, 2), (1, 2)]) # K3
    
    for algorithm in ["largest_first", "smallest_last", "DSATUR"]:
        coloring = solver.solve_coloring(graph, algorithm=algorithm)
        assert len(set(coloring.values())) >= 3

    with pytest.raises(ValueError):
        solver.solve_coloring(graph, algorithm="unknown")

def test_optimize_coloring():
    solver = GraphSolver()
    graph = nx.Graph()
    # Create a graph that can be optimized
    # Example: a path graph 0-1-2-3
    # Greedy might color it 0,1,0,1 (2 colors)
    # But if we have a more complex graph where greedy might use more colors than optimal
    # Let's use a simple case where a node can be recolored to a smaller color
    graph.add_edges_from([(0, 1), (1, 2), (2, 3)]) # Path graph P4
    initial_coloring = {0: 0, 1: 1, 2: 0, 3: 1} # A valid 2-coloring
    
    # Introduce a scenario where optimization might reduce colors
    # For example, if node 2 was colored 2 instead of 0
    initial_coloring_suboptimal = {0: 0, 1: 1, 2: 2, 3: 1} # 3 colors
    
    optimized_coloring = solver.optimize_coloring(graph, initial_coloring_suboptimal)
    
    # The optimized coloring should use fewer or equal colors, and still be valid
    assert len(set(optimized_coloring.values())) <= len(set(initial_coloring_suboptimal.values()))
    
    # Check validity
    for u, v in graph.edges():
        assert optimized_coloring[u] != optimized_coloring[v]

def test_get_num_layers():
    solver = GraphSolver()
    coloring = {0: 0, 1: 1, 2: 0, 3: 2}
    assert solver.get_num_layers(coloring) == 3
    assert solver.get_num_layers({}) == 0

def test_force_k_coloring():
    solver = GraphSolver()
    graph = nx.Graph()
    graph.add_edge(0, 1, weight=10)
    graph.add_edge(0, 2, weight=1)
    graph.add_edge(1, 2, weight=1)
    graph.add_node(0, size=100)
    graph.add_node(1, size=10)
    graph.add_node(2, size=1)

    # Test with k=2
    coloring = solver.force_k_coloring(graph, k=2)
    assert len(set(coloring.values())) == 2
    
    # Calculate the cost of the coloring
    cost = 0
    for u, v, data in graph.edges(data=True):
        if coloring[u] == coloring[v]:
            cost += data['weight']
            
    assert cost == 1


def test_empty_graph():
    solver = GraphSolver()
    graph = nx.Graph()
    
    coloring = solver.solve_coloring(graph)
    assert coloring == {}

    num_layers = solver.get_num_layers(coloring)
    assert num_layers == 0