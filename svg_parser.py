from typing import Dict, List, Optional, Tuple
from lxml import etree
import numpy as np
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, Point, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid
from shapely import affinity # Import affinity for scaling and translation
from svgpathtools import parse_path, Line
import math
import re

class Shape:
    def __init__(self, id, geometry, metadata, d_attribute=None):
        self.id = id
        self.geometry = geometry
        self.metadata = metadata
        self.d_attribute = d_attribute # Store d_attribute if provided

class SVGParser:
    # Points sampled per curved segment (Bezier/arc) when polygonizing paths.
    CURVE_SAMPLES = 16
    TRANSFORM_PATTERN = re.compile(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)')

    def load_svg(self, filepath: str) -> Tuple[List[Shape], float, float]:
        """Loads an SVG file and extracts shapes and dimensions."""
        tree = etree.parse(filepath)
        root = tree.getroot()
        shapes = self.extract_shapes(root)
        width, height = self.get_svg_dimensions(root)
        return shapes, width, height

    def parse_dimension(self, dimension_str) -> float:
        """Parse a dimension string and convert to float, handling units."""
        if not dimension_str:
            return 0.0
        
        # Convert to string if it's not already
        dimension_str = str(dimension_str).strip()
        
        if not dimension_str:
            return 0.0
        
        # Remove common units and convert to float
        # Handle px, pt, pc, mm, cm, in, em, ex, %
        units_pattern = r'(px|pt|pc|mm|cm|in|em|ex|%)$'
        
        # Remove units from the end of the string
        clean_value = re.sub(units_pattern, '', dimension_str, flags=re.IGNORECASE)
        
        try:
            return float(clean_value)
        except ValueError:
            # If we still can't parse it, try to extract just the numeric part
            numeric_match = re.match(r'([+-]?\d*\.?\d+)', clean_value)
            if numeric_match:
                return float(numeric_match.group(1))
            return 0.0

    def get_svg_dimensions(self, root) -> Tuple[float, float]:
        """Get SVG dimensions, handling units properly."""
        width_str = root.get('width', '0')
        height_str = root.get('height', '0')
        
        width = self.parse_dimension(width_str)
        height = self.parse_dimension(height_str)
        
        # Handle viewBox if width/height are not explicitly set or are 0
        if width == 0 and height == 0:
            viewbox = root.get('viewBox')
            if viewbox:
                parts = viewbox.split()
                if len(parts) == 4:
                    try:
                        width = float(parts[2])
                        height = float(parts[3])
                    except ValueError:
                        width = 800  # Default fallback
                        height = 600
        
        # If we still don't have dimensions, use reasonable defaults
        if width == 0:
            width = 800
        if height == 0:
            height = 600
            
        return width, height

    def extract_shapes(self, root) -> List[Shape]:
        """Extracts shapes from SVG elements."""
        shapes = []
        for i, element in enumerate(root.iter('{*}rect', '{*}circle', '{*}ellipse', '{*}polygon', '{*}path')):
            polygon = self.convert_to_polygon(element)
            if polygon:
                matrix = self.combined_transform(element)
                polygon, transformed = self.apply_transform(polygon, matrix)
                if polygon is None or polygon.is_empty:
                    continue
                metadata = self.preserve_metadata(element)
                d_attr = None
                # Keep the original path data only when no transform was applied,
                # so exported paths always match the analyzed geometry.
                if element.tag.endswith('path') and not transformed:
                    d_attr = element.get('d', '')
                shapes.append(Shape(id=i, geometry=polygon, metadata=metadata, d_attribute=d_attr))
        return shapes

    def combined_transform(self, element) -> np.ndarray:
        """Compose the transform matrices of the element and all its ancestors."""
        matrices = []
        node = element
        while node is not None:
            transform_attr = node.get('transform') if hasattr(node, 'get') else None
            if transform_attr:
                matrices.append(self.parse_transform(transform_attr))
            node = node.getparent()

        total = np.identity(3)
        # Ancestors apply first (outermost transform is leftmost).
        for matrix in reversed(matrices):
            total = total @ matrix
        return total

    def parse_transform(self, transform_str: str) -> np.ndarray:
        """Parse an SVG transform attribute into a 3x3 affine matrix."""
        matrix = np.identity(3)
        if not transform_str:
            return matrix
        for name, args_str in self.TRANSFORM_PATTERN.findall(transform_str):
            args = [float(value) for value in re.split(r'[\s,]+', args_str.strip()) if value]
            matrix = matrix @ self._transform_matrix(name, args)
        return matrix

    def _transform_matrix(self, name: str, args: List[float]) -> np.ndarray:
        try:
            if name == 'matrix' and len(args) == 6:
                a, b, c, d, e, f = args
                return np.array([[a, c, e], [b, d, f], [0.0, 0.0, 1.0]])
            if name == 'translate' and args:
                tx = args[0]
                ty = args[1] if len(args) > 1 else 0.0
                return np.array([[1.0, 0.0, tx], [0.0, 1.0, ty], [0.0, 0.0, 1.0]])
            if name == 'scale' and args:
                sx = args[0]
                sy = args[1] if len(args) > 1 else sx
                return np.array([[sx, 0.0, 0.0], [0.0, sy, 0.0], [0.0, 0.0, 1.0]])
            if name == 'rotate' and args:
                angle = math.radians(args[0])
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                rotation = np.array([[cos_a, -sin_a, 0.0], [sin_a, cos_a, 0.0], [0.0, 0.0, 1.0]])
                if len(args) >= 3:
                    cx, cy = args[1], args[2]
                    to_origin = self._transform_matrix('translate', [-cx, -cy])
                    back = self._transform_matrix('translate', [cx, cy])
                    return back @ rotation @ to_origin
                return rotation
            if name == 'skewX' and args:
                return np.array([[1.0, math.tan(math.radians(args[0])), 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
            if name == 'skewY' and args:
                return np.array([[1.0, 0.0, 0.0], [math.tan(math.radians(args[0])), 1.0, 0.0], [0.0, 0.0, 1.0]])
        except (ValueError, IndexError):
            pass
        return np.identity(3)

    def apply_transform(self, geometry, matrix: np.ndarray) -> Tuple[Optional[BaseGeometry], bool]:
        """Apply a 3x3 affine matrix to a geometry. Returns (geometry, was_transformed)."""
        if np.allclose(matrix, np.identity(3)):
            return geometry, False
        a, c, e = matrix[0]
        b, d, f = matrix[1]
        try:
            return affinity.affine_transform(geometry, [a, c, b, d, e, f]), True
        except Exception as transform_error:
            print(f"Warning: Could not apply transform: {transform_error}")
            return geometry, False

    def convert_to_polygon(self, element) -> Polygon:
        """Converts an SVG element to a Shapely Polygon."""
        try:
            if element.tag.endswith('rect'):
                x = self.parse_dimension(element.get('x', 0))
                y = self.parse_dimension(element.get('y', 0))
                width = self.parse_dimension(element.get('width', 0))
                height = self.parse_dimension(element.get('height', 0))
                if width == 0 or height == 0:
                    return None
                return box(x, y, x + width, y + height)
            elif element.tag.endswith('circle'):
                cx = self.parse_dimension(element.get('cx', 0))
                cy = self.parse_dimension(element.get('cy', 0))
                r = self.parse_dimension(element.get('r', 0))
                if r == 0:
                    return None
                return Point(cx, cy).buffer(r)
            elif element.tag.endswith('ellipse'):
                cx = self.parse_dimension(element.get('cx', 0))
                cy = self.parse_dimension(element.get('cy', 0))
                rx = self.parse_dimension(element.get('rx', 0))
                ry = self.parse_dimension(element.get('ry', 0))
                if rx == 0 or ry == 0:
                    return None
                # Correct approximation for ellipse: create a unit circle, scale it, then translate
                # Use affinity.scale for scaling with origin
                unit_circle = Point(0, 0).buffer(1) # Create a unit circle centered at origin
                scaled_ellipse = affinity.scale(unit_circle, xfact=rx, yfact=ry, origin=(0,0))
                # Translate to the correct center
                return affinity.translate(scaled_ellipse, xoff=cx, yoff=cy)
            elif element.tag.endswith('polygon'):
                points_str = element.get('points', '')
                if not points_str.strip():
                    return None
                points = []
                # Split by space, then by comma
                # The points attribute is a list of x,y pairs separated by spaces, with x and y separated by commas.
                # Example: "0,0 10,0 5,10"
                for p_pair_str in points_str.split(): # Split by space to get "x,y" pairs
                    coords = p_pair_str.split(',') # Split "x,y" by comma
                    if len(coords) == 2:
                        try:
                            x_coord = self.parse_dimension(coords[0])
                            y_coord = self.parse_dimension(coords[1])
                            points.append((x_coord, y_coord))
                        except ValueError:
                            print(f"Warning: Malformed coordinate pair in polygon points: {p_pair_str}")
                            return None
                    else:
                        print(f"Warning: Invalid coordinate pair format in polygon points: {p_pair_str}")
                        return None
                if len(points) < 3:
                    return None
                return Polygon(points)
            elif element.tag.endswith('path'):
                path_data = element.get('d', '')
                if not path_data.strip():
                    return None
                try:
                    return self.path_to_polygon(path_data, fill_rule=self._element_fill_rule(element))
                except Exception as path_error:
                    print(f"Warning: Could not parse path data '{path_data}': {path_error}")
                    return None
        except Exception as e:
            print(f"Could not convert element to polygon: {e}")
        return None

    def _element_fill_rule(self, element) -> str:
        """Read the element's fill-rule (attribute or style); SVG defaults to nonzero."""
        rule = element.get('fill-rule')
        if not rule:
            style = element.get('style') or ''
            match = re.search(r'(?:^|;)\s*fill-rule\s*:\s*([^;]+)', style, flags=re.IGNORECASE)
            rule = match.group(1) if match else None
        return 'evenodd' if rule and rule.strip().lower() == 'evenodd' else 'nonzero'

    def path_to_polygon(self, path_data: str, fill_rule: str = "nonzero") -> Optional[BaseGeometry]:
        """
        Convert path data to geometry: curves are sampled (not collapsed to
        endpoints) and multiple subpaths are combined according to the fill
        rule, so compound paths with holes produce correct geometry.
        """
        path = parse_path(path_data)
        rings = []
        for subpath in path.continuous_subpaths():
            ring = self._subpath_to_ring(subpath)
            if ring is not None:
                rings.append(ring)

        if not rings:
            return None

        if fill_rule == "evenodd":
            geometry = rings[0][0]
            for ring, _ in rings[1:]:
                geometry = geometry.symmetric_difference(ring)
        else:
            geometry = self._combine_nonzero(rings)

        geometry = self._only_polygonal(geometry)
        if geometry is None or geometry.is_empty:
            return None
        return geometry

    def _combine_nonzero(self, rings: List[Tuple[BaseGeometry, float]]) -> BaseGeometry:
        """
        Approximate the nonzero fill rule using winding direction: subpaths
        winding like the dominant (largest) contour add area, opposite ones
        cut holes. Exact for the compound shapes design tools emit.
        """
        dominant_signed_area = max(rings, key=lambda item: abs(item[1]))[1]
        dominant_ccw = dominant_signed_area >= 0
        additive = [geom for geom, signed_area in rings if (signed_area >= 0) == dominant_ccw]
        subtractive = [geom for geom, signed_area in rings if (signed_area >= 0) != dominant_ccw]

        geometry = unary_union(additive)
        if subtractive:
            geometry = geometry.difference(unary_union(subtractive))
        return geometry

    def _subpath_to_ring(self, subpath) -> Optional[Tuple[BaseGeometry, float]]:
        """Sample one continuous subpath into (polygon, signed area of the raw ring)."""
        coords = []
        for segment in subpath:
            coords.extend(self._sample_segment_points(segment))
        coords.append((subpath.end.real, subpath.end.imag))

        if len(coords) < 3:
            return None

        signed_area = self._signed_area(coords)
        ring = Polygon(coords)
        if not ring.is_valid:
            ring = self._only_polygonal(make_valid(ring))
        if ring is None or ring.is_empty or ring.area == 0:
            return None
        return ring, signed_area

    @staticmethod
    def _signed_area(coords: List[Tuple[float, float]]) -> float:
        """Shoelace signed area of a coordinate ring (sign encodes winding)."""
        area = 0.0
        count = len(coords)
        for i in range(count):
            x1, y1 = coords[i]
            x2, y2 = coords[(i + 1) % count]
            area += x1 * y2 - x2 * y1
        return area / 2.0

    def _sample_segment_points(self, segment) -> List[Tuple[float, float]]:
        """Return points along a segment, excluding its end point (the next segment provides it)."""
        if isinstance(segment, Line):
            return [(segment.start.real, segment.start.imag)]
        points = []
        for step in range(self.CURVE_SAMPLES):
            point = segment.point(step / self.CURVE_SAMPLES)
            points.append((point.real, point.imag))
        return points

    def _only_polygonal(self, geometry) -> Optional[BaseGeometry]:
        """Reduce a geometry to its polygonal parts (drops stray lines/points)."""
        if geometry is None:
            return None
        if isinstance(geometry, (Polygon, MultiPolygon)):
            return geometry
        if isinstance(geometry, GeometryCollection):
            polygons = [geom for geom in geometry.geoms if isinstance(geom, (Polygon, MultiPolygon))]
            if polygons:
                return unary_union(polygons)
        return None

    def preserve_metadata(self, element) -> Dict:
        """Preserves relevant metadata from the SVG."""
        return {
            'style': element.get('style'),
            'transform': element.get('transform'),
            'id': element.get('id'),
            'fill': element.get('fill'),
            'fill-rule': element.get('fill-rule'),
            'stroke': element.get('stroke'),
        }
