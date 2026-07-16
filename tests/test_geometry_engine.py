import pytest
from geometry_engine import GeometryEngine
from svg_parser import Shape
from shapely.geometry import Polygon, Point, box

# Fixture for creating simple shapes
@pytest.fixture
def simple_shapes():
    shape1 = Shape(id=0, geometry=box(0, 0, 10, 10), metadata={})
    shape2 = Shape(id=1, geometry=box(5, 5, 15, 15), metadata={}) # Overlaps with shape1
    shape3 = Shape(id=2, geometry=box(20, 20, 30, 30), metadata={}) # No overlap
    shape4 = Shape(id=3, geometry=Point(7, 7).buffer(3), metadata={}) # Overlaps with shape1 and shape2
    return [shape1, shape2, shape3, shape4]

def test_detect_overlaps_no_spatial_index(simple_shapes):
    engine = GeometryEngine(use_spatial_index=False)
    overlaps = engine.detect_overlaps(simple_shapes)
    # Expected overlaps: (0,1), (0,3), (1,3)
    detected_pairs = sorted([(i, j) for i, j, area in overlaps])
    expected_overlaps = sorted([(0,1), (0,3), (1,3)])
    assert detected_pairs == expected_overlaps
    for _, _, area in overlaps:
        assert area > 0

def test_detect_overlaps_spatial_index(simple_shapes):
    engine = GeometryEngine(use_spatial_index=True)
    overlaps = engine.detect_overlaps(simple_shapes)
    # Expected overlaps: (0,1), (0,3), (1,3)
    detected_pairs = sorted([(i, j) for i, j, area in overlaps])
    expected_overlaps = sorted([(0,1), (0,3), (1,3)])
    assert detected_pairs == expected_overlaps
    for _, _, area in overlaps:
        assert area > 0


def test_detect_overlap_pairs(simple_shapes):
    engine = GeometryEngine(use_spatial_index=True)
    pairs = sorted(engine.detect_overlap_pairs(simple_shapes))
    assert pairs == sorted([(0, 1), (0, 3), (1, 3)])

def test_parallel_overlap_detection(simple_shapes):
    engine = GeometryEngine(max_workers=2) # Use 2 workers for testing parallel
    overlaps = engine.parallel_overlap_detection(simple_shapes)
    # Expected overlaps: (0,1), (0,3), (1,3)
    detected_pairs = sorted([(i, j) for i, j, area in overlaps])
    expected_overlaps = sorted([(0,1), (0,3), (1,3)])
    assert detected_pairs == expected_overlaps
    for _, _, area in overlaps:
        assert area > 0

def test_empty_shapes_list():
    engine = GeometryEngine()
    overlaps = engine.detect_overlaps([])
    assert overlaps == []

def test_single_shape_list():
    engine = GeometryEngine()
    shape = Shape(id=0, geometry=box(0,0,10,10), metadata={})
    overlaps = engine.detect_overlaps([shape])
    assert overlaps == []


def test_detect_contacts_includes_touching_pairs():
    engine = GeometryEngine(use_spatial_index=True)
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(10, 0, 20, 10), metadata={}),  # Touches shape 0 at an edge
        Shape(id=2, geometry=box(30, 0, 40, 10), metadata={}),  # Disjoint
    ]

    contacts = sorted(engine.detect_contacts(shapes))
    assert contacts == [(0, 1)]


def test_detect_contacts_corner_touch_allowed_policy():
    engine = GeometryEngine(use_spatial_index=True)
    shapes = [
        Shape(id=0, geometry=box(0, 0, 10, 10), metadata={}),
        Shape(id=1, geometry=box(10, 10, 20, 20), metadata={}),  # Corner touch only
    ]

    strict_contacts = sorted(engine.detect_contacts(shapes, touch_policy="any_touch"))
    corner_allowed_contacts = sorted(engine.detect_contacts(shapes, touch_policy="edge_or_overlap"))

    assert strict_contacts == [(0, 1)]
    assert corner_allowed_contacts == []


def test_detect_contacts_handles_invalid_geometry():
    engine = GeometryEngine(use_spatial_index=True)
    bowtie = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])  # invalid
    shapes = [
        Shape(id=0, geometry=bowtie, metadata={}),
        Shape(id=1, geometry=box(0, 0, 1, 1), metadata={}),
    ]

    contacts = engine.detect_contacts(shapes, touch_policy="any_touch")
    assert isinstance(contacts, list)


def _random_shapes(count, seed):
    import random
    rng = random.Random(seed)
    shapes = []
    for i in range(count):
        x, y = rng.uniform(0, 200), rng.uniform(0, 200)
        if i % 3 == 0:
            shapes.append(Shape(id=i, geometry=Point(x, y).buffer(rng.uniform(3, 12)), metadata={}))
        else:
            w, h = rng.uniform(5, 25), rng.uniform(5, 25)
            shapes.append(Shape(id=i, geometry=box(x, y, x + w, y + h), metadata={}))
    return shapes


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_vectorized_overlaps_match_pairwise(seed):
    engine = GeometryEngine(use_spatial_index=True)
    shapes = _random_shapes(80, seed)

    vectorized = engine._detect_overlaps_vectorized(shapes)
    pairwise = engine._detect_overlaps_pairwise(shapes)

    assert sorted((i, j) for i, j, _ in vectorized) == sorted((i, j) for i, j, _ in pairwise)
    vec_areas = {(i, j): a for i, j, a in vectorized}
    for i, j, area in pairwise:
        assert abs(vec_areas[(i, j)] - area) < 1e-9


@pytest.mark.parametrize("policy", ["any_touch", "edge_or_overlap"])
def test_vectorized_contacts_match_pairwise(policy):
    engine = GeometryEngine(use_spatial_index=True)
    shapes = _random_shapes(80, 3) + [
        Shape(id=1000, geometry=box(300, 300, 310, 310), metadata={}),
        Shape(id=1001, geometry=box(310, 300, 320, 310), metadata={}),  # edge touch
        Shape(id=1002, geometry=box(310, 310, 320, 320), metadata={}),  # corner touch
    ]

    vectorized = sorted(engine._detect_contacts_vectorized(shapes, policy))
    pairwise = sorted(engine._detect_contacts_pairwise(shapes, policy))
    assert vectorized == pairwise


def test_vectorized_overlaps_handle_invalid_geometry():
    engine = GeometryEngine(use_spatial_index=True)
    bowtie = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
    shapes = [
        Shape(id=0, geometry=bowtie, metadata={}),
        Shape(id=1, geometry=box(0, 0, 1, 1), metadata={}),
    ]
    overlaps = engine.detect_overlaps(shapes)
    assert isinstance(overlaps, list)


def test_detect_contacts_rejects_unknown_touch_policy(simple_shapes):
    engine = GeometryEngine(use_spatial_index=True)
    with pytest.raises(ValueError):
        engine.detect_contacts(simple_shapes, touch_policy="bogus")
