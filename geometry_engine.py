from typing import Iterable, List, Tuple
from shapely.geometry import Polygon
from shapely.validation import make_valid
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

    def detect_overlap_pairs(self, shapes: List[Shape]) -> List[Tuple[int, int]]:
        """
        Detect overlap adjacency pairs without calculating overlap area.
        """
        pairs = []
        for i, j in self._candidate_pairs(shapes):
            shape1 = shapes[i]
            shape2 = shapes[j]
            if self._bounds_intersect(shape1.geometry.bounds, shape2.geometry.bounds):
                g1 = self._sanitize_geometry(shape1.geometry)
                g2 = self._sanitize_geometry(shape2.geometry)
                if g1.intersects(g2):
                    intersection = g1.intersection(g2)
                    if not intersection.is_empty and intersection.area > 0:
                        pairs.append((i, j))
        return pairs

    def detect_overlaps_spatial(self, shapes: List[Shape]) -> List[Tuple[int, int, float]]:
        """Detects overlaps using a spatial index."""
        overlaps = []
        for i, j in self._candidate_pairs(shapes):
            shape1 = shapes[i]
            shape2 = shapes[j]
            if self._bounds_intersect(shape1.geometry.bounds, shape2.geometry.bounds):
                g1 = self._sanitize_geometry(shape1.geometry)
                g2 = self._sanitize_geometry(shape2.geometry)
                if g1.intersects(g2):
                    overlap_area = g1.intersection(g2).area
                    if overlap_area > 0:
                        overlaps.append((i, j, overlap_area))
        return overlaps

    def detect_contacts(self, shapes: List[Shape], touch_policy: str = "any_touch") -> List[Tuple[int, int]]:
        """
        Detects all shape pairs that should be treated as conflicting contacts.

        touch_policy:
            - "any_touch": edge touch, corner touch, or overlap are all conflicts.
            - "edge_or_overlap": only shared edge/segment or overlap are conflicts;
              corner-only (point) touches are allowed.
        """
        contacts = []
        for i, j in self._candidate_pairs(shapes):
            shape1 = shapes[i]
            shape2 = shapes[j]
            if self._bounds_intersect(shape1.geometry.bounds, shape2.geometry.bounds) and self._is_contact_conflict(
                shape1.geometry, shape2.geometry, touch_policy
            ):
                contacts.append((i, j))
        return contacts

    def parallel_overlap_detection(self, shapes: List[Shape]) -> List[Tuple[int, int, float]]:
        """Detects overlaps in parallel and calculates their area."""
        shape_pairs = [(i, j, shapes[i].geometry, shapes[j].geometry) for i, j in combinations(range(len(shapes)), 2)]
        
        with multiprocessing.Pool(processes=self.max_workers) as pool:
            results = pool.map(check_and_calculate_overlap_worker, shape_pairs)
        
        return [res for res in results if res is not None]

    def calculate_overlap_area(self, shape1: Shape, shape2: Shape) -> float:
        """Calculates the overlap area between two shapes."""
        g1 = self._sanitize_geometry(shape1.geometry)
        g2 = self._sanitize_geometry(shape2.geometry)
        if g1.intersects(g2):
            return g1.intersection(g2).area
        return 0.0

    def _candidate_pairs(self, shapes: List[Shape]) -> Iterable[Tuple[int, int]]:
        """
        Returns candidate shape index pairs using the configured strategy.
        """
        if not self.use_spatial_index:
            return combinations(range(len(shapes)), 2)

        self.build_spatial_index(shapes)
        seen = set()
        for i, shape in enumerate(shapes):
            for j in self.idx.intersection(shape.geometry.bounds):
                if j <= i:
                    continue
                key = (i, j)
                if key not in seen:
                    seen.add(key)
                    yield key

    def _bounds_intersect(self, b1, b2) -> bool:
        return not (b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1])

    def _is_contact_conflict(self, geom1: Polygon, geom2: Polygon, touch_policy: str) -> bool:
        geom1 = self._sanitize_geometry(geom1)
        geom2 = self._sanitize_geometry(geom2)

        # Fast path for the default policy: any contact is a conflict.
        if touch_policy == "any_touch":
            return geom1.intersects(geom2)

        if not geom1.intersects(geom2):
            return False

        intersection = geom1.intersection(geom2)
        if intersection.is_empty:
            return False

        if touch_policy == "edge_or_overlap":
            # Overlap area or line/segment touch are conflicts.
            # Corner-only point contact has zero area and zero length and is allowed.
            return intersection.area > 0 or intersection.length > 0

        return True

    def _sanitize_geometry(self, geom: Polygon) -> Polygon:
        if geom.is_valid:
            return geom
        try:
            repaired = make_valid(geom)
            if not repaired.is_empty:
                return repaired
        except Exception:
            pass
        try:
            repaired = geom.buffer(0)
            if not repaired.is_empty:
                return repaired
        except Exception:
            pass
        return geom
