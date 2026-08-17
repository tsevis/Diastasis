"""
Shared geometry repair helpers.

Boolean operations on artwork imported from the wild routinely hit
self-intersecting or otherwise invalid polygons. Every helper here degrades
gracefully: it returns the best geometry it can rather than raising, so one
malformed shape never aborts a whole separation run.
"""

from typing import List, Optional

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid


def sanitize_geometry(geometry: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
    """Return a valid equivalent of geometry, or the original if unrepairable."""
    if geometry is None or geometry.is_empty:
        return geometry
    if geometry.is_valid:
        return geometry

    try:
        repaired = make_valid(geometry)
        if not repaired.is_empty:
            return repaired
    except Exception:
        pass

    try:
        repaired = geometry.buffer(0)
        if not repaired.is_empty:
            return repaired
    except Exception:
        pass

    return geometry


def safe_difference(geom: Optional[BaseGeometry], mask: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
    """geom minus mask, falling back to the unmodified geom on failure."""
    geom = sanitize_geometry(geom)
    mask = sanitize_geometry(mask)
    if geom is None or geom.is_empty:
        return geom
    if mask is None or mask.is_empty:
        return geom

    try:
        return geom.difference(mask)
    except Exception:
        try:
            sanitized_geom = sanitize_geometry(geom)
            sanitized_mask = sanitize_geometry(mask)
            if sanitized_geom is None or sanitized_mask is None:
                return geom
            return sanitized_geom.difference(sanitized_mask)
        except Exception:
            return geom


def safe_unary_union(geometries: List[BaseGeometry]) -> Optional[BaseGeometry]:
    """unary_union with a sanitizing fallback for invalid inputs."""
    try:
        return unary_union(geometries)
    except Exception:
        try:
            return unary_union([sanitize_geometry(g) for g in geometries])
        except Exception:
            # Last resort: fold pairwise so one bad geometry can't lose the rest.
            merged: Optional[BaseGeometry] = None
            for geometry in geometries:
                if merged is None:
                    merged = geometry
                    continue
                try:
                    sanitized_merged = sanitize_geometry(merged)
                    sanitized_next = sanitize_geometry(geometry)
                    if sanitized_merged is None or sanitized_next is None:
                        continue
                    merged = sanitized_merged.union(sanitized_next)
                except Exception:
                    continue
            return merged
