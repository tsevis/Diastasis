from typing import List, Dict, Tuple
from lxml import etree
from shapely.geometry import Polygon, Point, box
from shapely import affinity # Import affinity for scaling and translation
from svgpathtools import parse_path
import math
import re

class Shape:
    def __init__(self, id, geometry, metadata, d_attribute=None):
        self.id = id
        self.geometry = geometry
        self.metadata = metadata
        self.d_attribute = d_attribute # Store d_attribute if provided

class SVGParser:
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
                metadata = self.preserve_metadata(element)
                d_attr = None
                if element.tag.endswith('path'):
                    d_attr = element.get('d', '')
                shapes.append(Shape(id=i, geometry=polygon, metadata=metadata, d_attribute=d_attr))
        return shapes

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
                    path = parse_path(path_data)
                    coords = []
                    for segment in path:
                        coords.append((segment.start.real, segment.start.imag))
                    # Ensure the path is closed for polygon conversion if it's not already
                    if path.isclosed():
                        coords.append((path.start.real, path.start.imag))
                    else:
                        coords.append((path.end.real, path.end.imag))

                    if len(coords) < 3:
                        return None
                    return Polygon(coords)
                except Exception as path_error:
                    print(f"Warning: Could not parse path data '{path_data}': {path_error}")
                    return None
        except Exception as e:
            print(f"Could not convert element to polygon: {e}")
        return None

    def preserve_metadata(self, element) -> Dict:
        """Preserves relevant metadata from the SVG."""
        return {
            'style': element.get('style'),
            'transform': element.get('transform'),
            'id': element.get('id'),
        }