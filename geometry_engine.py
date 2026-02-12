from typing import List, Tuple
from shapely.geometry import Polygon, box
from rtree import index
from svg_parser import Shape
import multiprocessing
from itertools import combinations

def check_and_calculate_overlap_worker(shapes_pair: Tuple[int, int, Polygon, Polygon]) -> Tuple[int, int, float]:
    """Worker function to check for overlap and calculate the area."""
    i, j, shape1_geom, shape2_geom = shapes_pair
    if shape1_geom.intersects(shape2_geom):
        overlap_area = shape1_geom.intersection(shape2_geom).area
        if overlap_area > 0:
            return (i, j, overlap_area)
    return None

class GeometryEngine:
    def __init__(self, use_spatial_index=True, max_workers=None):
        self.use_spatial_index = use_spatial_index
        self.max_workers = max_workers if max_workers else multiprocessing.cpu_count()
        self.idx = None

    def build_spatial_index(self, shapes: List[Shape]):
        """Builds a spatial index for the given shapes."""
        if not self.use_spatial_index:
            return
        self.idx = index.Index()
        for i, shape in enumerate(shapes):
            self.idx.insert(i, shape.geometry.bounds)

    def detect_overlaps(self, shapes: List[Shape]) -> List[Tuple[int, int, float]]:
        """Detects all pairs of overlapping shapes and their overlap area."""
        if self.use_spatial_index:
            return self.detect_overlaps_spatial(shapes)
        else:
            return self.parallel_overlap_detection(shapes)

    def detect_overlaps_spatial(self, shapes: List[Shape]) -> List[Tuple[int, int, float]]:
        """Detects overlaps using a spatial index."""
        self.build_spatial_index(shapes)
        overlaps = []
        # Use combinations to avoid duplicate checks
        for i, j in combinations(range(len(shapes)), 2):
            shape1 = shapes[i]
            shape2 = shapes[j]
            # Check if bounding boxes intersect first
            bbox1 = box(*shape1.geometry.bounds)
            bbox2 = box(*shape2.geometry.bounds)
            if bbox1.intersects(bbox2):
                if shape1.geometry.intersects(shape2.geometry):
                    overlap_area = shape1.geometry.intersection(shape2.geometry).area
                    if overlap_area > 0:
                        overlaps.append((i, j, overlap_area))
        return overlaps

    def parallel_overlap_detection(self, shapes: List[Shape]) -> List[Tuple[int, int, float]]:
        """Detects overlaps in parallel and calculates their area."""
        shape_pairs = [(i, j, shapes[i].geometry, shapes[j].geometry) for i, j in combinations(range(len(shapes)), 2)]
        
        with multiprocessing.Pool(processes=self.max_workers) as pool:
            results = pool.map(check_and_calculate_overlap_worker, shape_pairs)
        
        return [res for res in results if res is not None]

    def calculate_overlap_area(self, shape1: Shape, shape2: Shape) -> float:
        """Calculates the overlap area between two shapes."""
        if shape1.geometry.intersects(shape2.geometry):
            return shape1.geometry.intersection(shape2.geometry).area
        return 0.0
