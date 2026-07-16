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
    def __init__(self, id, geometry, metadata, d_attribute=None, native_shape=None):
        self.id = id
        self.geometry = geometry
        self.metadata = metadata
        self.d_attribute = d_attribute # Store d_attribute if provided
        # Original element tag/attrs for lossless export, valid only while
        # the geometry is untouched (pipelines that alter geometry drop it).
        self.native_shape = native_shape

class SVGParser:
    # Points sampled per curved segment (Bezier/arc) when polygonizing paths.
    CURVE_SAMPLES = 16
    TRANSFORM_PATTERN = re.compile(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)')

    def __init__(self, include_strokes: bool = False):
        # When set, each shape's geometry becomes its painted footprint:
        # the fill area grown by half the (inherited) stroke width.
        self.include_strokes = include_strokes

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
        """Get the canvas size in the shapes' coordinate system."""
        # Shape coordinates live in the viewBox coordinate system when one is
        # declared (width/height may carry physical units like mm), so the
        # viewBox must win for the canvas to match the analyzed geometry.
        viewbox = root.get('viewBox')
        if viewbox:
            parts = re.split(r'[\s,]+', viewbox.strip())
            if len(parts) == 4:
                try:
                    width, height = float(parts[2]), float(parts[3])
                    if width > 0 and height > 0:
                        return width, height
                except ValueError:
                    pass

        width = self.parse_dimension(root.get('width', '0'))
        height = self.parse_dimension(root.get('height', '0'))

        # If we still don't have dimensions, use reasonable defaults
        if width == 0:
            width = 800
        if height == 0:
            height = 600

        return width, height

    # Content inside these containers is not rendered directly; it only
    # appears where a <use> references it.
    NON_RENDERED_CONTAINERS = {'defs', 'symbol', 'clipPath', 'mask', 'pattern', 'marker'}

    # Attributes captured for lossless native re-emission per element kind.
    NATIVE_ATTRS = {
        'rect': ('x', 'y', 'width', 'height', 'rx', 'ry'),
        'circle': ('cx', 'cy', 'r'),
        'ellipse': ('cx', 'cy', 'rx', 'ry'),
        'polygon': ('points',),
        'polyline': ('points',),
    }

    def extract_shapes(self, root) -> List[Shape]:
        """Extracts shapes from SVG elements, resolving <use> references."""
        shapes = []
        for element in root.iter('{*}rect', '{*}circle', '{*}ellipse', '{*}polygon', '{*}polyline', '{*}path'):
            if not self._is_rendered(element):
                continue
            shape = self._element_to_shape(element, self.combined_transform(element), len(shapes))
            if shape is not None:
                shapes.append(shape)

        id_map = None
        for use in root.iter('{*}use'):
            if not self._is_rendered(use):
                continue
            if id_map is None:
                id_map = self._build_id_map(root)
            shape = self._resolve_use(id_map, use, len(shapes))
            if shape is not None:
                shapes.append(shape)

        return shapes

    @staticmethod
    def _build_id_map(root) -> Dict[str, object]:
        """Map id -> element once; first occurrence wins (getElementById semantics)."""
        id_map = {}
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            element_id = element.get('id')
            if element_id and element_id not in id_map:
                id_map[element_id] = element
        return id_map

    def _element_to_shape(
        self, element, matrix: np.ndarray, shape_id: int, paint_context=None
    ) -> Optional[Shape]:
        """
        Convert one SVG element plus its effective transform into a Shape.
        paint_context redirects paint inheritance (used for <use> clones,
        which inherit from the <use> element, not the target's location).
        """
        polygon = self.convert_to_polygon(element)
        if polygon is None:
            return None

        stroked = False
        if self.include_strokes:
            # SVG paints the stroke in user space before transforms apply,
            # so the footprint must be grown before the transform.
            polygon, stroked = self._apply_stroke_footprint(polygon, element, paint_context)

        polygon, transformed = self.apply_transform(polygon, matrix)
        if polygon is None or polygon.is_empty:
            return None

        localname = self._localname(element)
        metadata = self.preserve_metadata(element, paint_context)
        d_attr = None
        native_shape = None
        # Original markup stays valid for export only while the geometry is
        # untouched, so exported elements always match the analyzed geometry.
        if not transformed and not stroked:
            if localname == 'path':
                d_attr = element.get('d', '')
            else:
                native_shape = self._native_shape(element, localname)
        return Shape(
            id=shape_id,
            geometry=polygon,
            metadata=metadata,
            d_attribute=d_attr,
            native_shape=native_shape,
        )

    def _resolve_use(self, id_map: Dict[str, object], use, shape_id: int) -> Optional[Shape]:
        """Instantiate a <use> reference to a basic shape element."""
        href = use.get('href') or use.get('{http://www.w3.org/1999/xlink}href')
        if not href or not href.startswith('#'):
            return None
        target = id_map.get(href[1:])
        if target is None:
            return None
        if self._localname(target) not in ('rect', 'circle', 'ellipse', 'polygon', 'polyline', 'path'):
            return None

        # Effective transform: use's ancestor chain (includes use@transform),
        # then the x/y offset, then the target's own transform.
        offset = self._transform_matrix(
            'translate',
            [self.parse_dimension(use.get('x', 0)), self.parse_dimension(use.get('y', 0))],
        )
        matrix = self.combined_transform(use) @ offset @ self.parse_transform(target.get('transform') or '')
        # The clone lives in the <use> element's shadow tree, so paint
        # properties inherit from the <use> element and its ancestors.
        return self._element_to_shape(target, matrix, shape_id, paint_context=use)

    def _apply_stroke_footprint(self, geometry, element, paint_context=None) -> Tuple[BaseGeometry, bool]:
        """
        Grow a geometry by half its effective stroke width so the analyzed
        area matches the painted footprint. Returns (geometry, was_grown).
        Round joins are a close approximation of SVG's default miter joins;
        acute corners may extend slightly further when actually rendered.
        """
        stroke = self._effective_paint(element, 'stroke', paint_context)
        if not stroke or stroke.strip().lower() in ('none', 'transparent'):
            return geometry, False

        width_value = self._effective_paint(element, 'stroke-width', paint_context)
        stroke_width = self.parse_dimension(width_value) if width_value is not None else 1.0
        if stroke_width <= 0:
            return geometry, False

        try:
            return geometry.buffer(stroke_width / 2.0), True
        except Exception as buffer_error:
            print(f"Warning: Could not grow stroke footprint: {buffer_error}")
            return geometry, False

    def _is_rendered(self, element) -> bool:
        """False for content living inside defs/symbol/clipPath/mask/pattern/marker."""
        node = element.getparent()
        while node is not None:
            if isinstance(node.tag, str) and self._localname(node) in self.NON_RENDERED_CONTAINERS:
                return False
            node = node.getparent()
        return True

    # Plain unitless numbers and point lists: the only attribute values the
    # analyzer interprets identically to an SVG renderer.
    _PLAIN_NUMBER = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$')
    _PLAIN_POINTS = re.compile(r'^[\s,0-9eE+.\-]+$')

    def _native_shape(self, element, localname: str) -> Optional[Dict]:
        """Capture original tag/attrs for lossless export of basic shapes."""
        attr_names = self.NATIVE_ATTRS.get(localname)
        if not attr_names:
            return None
        attrs = {name: element.get(name) for name in attr_names if element.get(name) is not None}
        # Unit-suffixed values (10mm, 50%) are analyzed as bare numbers, so
        # re-emitting them verbatim would not match the analyzed geometry.
        for name, value in attrs.items():
            pattern = self._PLAIN_POINTS if name == 'points' else self._PLAIN_NUMBER
            if not pattern.match(value.strip()):
                return None
        tag = 'polygon' if localname == 'polyline' else localname
        return {'tag': tag, 'attrs': attrs}

    @staticmethod
    def _localname(element) -> str:
        tag = element.tag
        return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''

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
                rx, ry = self._rect_corner_radii(element, width, height)
                if rx > 0 and ry > 0:
                    return self._rounded_rect_polygon(x, y, width, height, rx, ry)
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
            elif element.tag.endswith('polygon') or element.tag.endswith('polyline'):
                # SVG fills a polyline as if it were closed, so both map to
                # the same polygon geometry.
                points = self._parse_points(element.get('points', ''))
                if points is None or len(points) < 3:
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

    def _rect_corner_radii(self, element, width: float, height: float) -> Tuple[float, float]:
        """Resolve rect rx/ry per SVG rules: each defaults to the other, clamped to half-size."""
        rx_attr = element.get('rx')
        ry_attr = element.get('ry')
        rx = self.parse_dimension(rx_attr) if rx_attr is not None else None
        ry = self.parse_dimension(ry_attr) if ry_attr is not None else None
        # SVG treats a negative radius as unspecified ("auto").
        if rx is not None and rx < 0:
            rx = None
        if ry is not None and ry < 0:
            ry = None
        if rx is None and ry is None:
            return 0.0, 0.0
        if rx is None:
            rx = ry
        if ry is None:
            ry = rx
        return max(0.0, min(rx, width / 2)), max(0.0, min(ry, height / 2))

    def _rounded_rect_polygon(
        self, x: float, y: float, width: float, height: float, rx: float, ry: float,
        corner_samples: int = 9,
    ) -> Polygon:
        """Build a rounded rectangle with sampled quarter-ellipse corners."""
        # Corner arc centers and their start angles, walking the outline in
        # one consistent direction (angles in the ellipse parameterization).
        corners = [
            (x + width - rx, y + height - ry, 0.0),   # bottom-right
            (x + rx, y + height - ry, 90.0),          # bottom-left
            (x + rx, y + ry, 180.0),                  # top-left
            (x + width - rx, y + ry, 270.0),          # top-right
        ]
        coords = []
        for cx, cy, start_deg in corners:
            for step in range(corner_samples):
                angle = math.radians(start_deg + 90.0 * step / (corner_samples - 1))
                coords.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle)))
        ring = Polygon(coords)
        if not ring.is_valid:
            ring = self._only_polygonal(make_valid(ring))
        return ring

    def _parse_points(self, points_str: str) -> Optional[List[Tuple[float, float]]]:
        """Parse a polygon/polyline points attribute into coordinate pairs."""
        values = [v for v in re.split(r'[\s,]+', points_str.strip()) if v]
        if len(values) < 2 or len(values) % 2 != 0:
            return None
        try:
            numbers = [float(v) for v in values]
        except ValueError:
            print(f"Warning: Malformed points attribute: {points_str!r}")
            return None
        return list(zip(numbers[0::2], numbers[1::2]))

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

    def preserve_metadata(self, element, paint_context=None) -> Dict:
        """Preserves relevant metadata, resolving inherited paint properties."""
        return {
            'style': element.get('style'),
            'transform': element.get('transform'),
            'id': element.get('id'),
            'fill': self._effective_paint(element, 'fill', paint_context),
            'fill-rule': element.get('fill-rule'),
            'stroke': self._effective_paint(element, 'stroke', paint_context),
            'stroke-width': self._effective_paint(element, 'stroke-width', paint_context),
        }

    def _style_property(self, style: Optional[str], prop: str) -> Optional[str]:
        """Read one property value out of an inline style attribute."""
        if not style:
            return None
        match = re.search(rf'(?:^|;)\s*{prop}\s*:\s*([^;]+)', style, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _own_paint(self, element, prop: str) -> Optional[str]:
        """
        The element's own value for a paint property. Per the CSS cascade,
        the inline style overrides the presentation attribute.
        """
        value = self._style_property(element.get('style'), prop) or element.get(prop)
        if value and value.strip().lower() == 'inherit':
            return None
        return value

    def _effective_paint(self, element, prop: str, inherit_from=None) -> Optional[str]:
        """
        Resolve a paint property with SVG inheritance: the element's own
        value wins, otherwise the nearest ancestor that sets it. When
        inherit_from is given (a <use> element), inheritance starts there
        (including its own attributes) instead of the element's parent.
        """
        value = self._own_paint(element, prop)
        node = inherit_from if inherit_from is not None else element.getparent()
        while value is None and node is not None:
            if isinstance(node.tag, str):
                value = self._own_paint(node, prop)
            node = node.getparent()
        return value
