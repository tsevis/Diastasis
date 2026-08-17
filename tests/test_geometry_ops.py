"""Tests for the shared geometry repair helpers.

These cover the degradation paths: every helper must return the best
geometry it can rather than raising, so one malformed shape never aborts
a separation run.
"""

import pytest
from shapely.geometry import GeometryCollection, Polygon, box

from diastasis.geometry_ops import safe_difference, safe_unary_union, sanitize_geometry


@pytest.fixture
def bowtie():
    """A self-intersecting ("bowtie") polygon, the classic invalid input."""
    return Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])


def test_sanitize_geometry_passes_through_none_and_empty():
    assert sanitize_geometry(None) is None
    empty = Polygon()
    assert sanitize_geometry(empty).is_empty


def test_sanitize_geometry_returns_valid_geometry_unchanged():
    valid = box(0, 0, 10, 10)
    assert sanitize_geometry(valid) is valid


def test_sanitize_geometry_repairs_invalid_geometry(bowtie):
    assert not bowtie.is_valid
    repaired = sanitize_geometry(bowtie)
    assert repaired.is_valid
    assert not repaired.is_empty


def test_safe_difference_subtracts_overlap():
    result = safe_difference(box(0, 0, 10, 10), box(5, 0, 15, 10))
    assert result.area == pytest.approx(50.0)


def test_safe_difference_returns_geom_when_mask_is_absent_or_empty():
    geom = box(0, 0, 10, 10)
    assert safe_difference(geom, None) is geom
    assert safe_difference(geom, Polygon()) is geom


def test_safe_difference_passes_through_missing_geom():
    assert safe_difference(None, box(0, 0, 1, 1)) is None
    assert safe_difference(Polygon(), box(0, 0, 1, 1)).is_empty


def test_safe_difference_repairs_invalid_operands(bowtie):
    """An invalid operand is repaired first, so the difference is real."""
    result = safe_difference(bowtie, box(0, 0, 1, 1))
    assert result.is_valid
    # The repaired bowtie has area 2.0; the mask clips 0.5 of it away.
    assert result.area == pytest.approx(1.5)


def test_safe_unary_union_merges_touching_boxes():
    merged = safe_unary_union([box(0, 0, 5, 10), box(5, 0, 10, 10)])
    assert merged.geom_type == "Polygon"
    assert merged.area == pytest.approx(100.0)


def test_safe_unary_union_of_single_geometry():
    merged = safe_unary_union([box(0, 0, 4, 4)])
    assert merged.area == pytest.approx(16.0)


def test_safe_unary_union_handles_invalid_members(bowtie):
    """A bad geometry in the list must not lose the others."""
    merged = safe_unary_union([bowtie, box(10, 10, 20, 20)])
    assert merged is not None
    assert not merged.is_empty
    # The clean box's area survives the union.
    assert merged.area >= 100.0


def test_safe_unary_union_falls_back_when_union_raises(monkeypatch):
    """When unary_union fails outright, the pairwise fold still merges."""
    import diastasis.geometry_ops as geometry_ops

    def always_fails(_geometries):
        raise ValueError("simulated GEOS failure")

    monkeypatch.setattr(geometry_ops, "unary_union", always_fails)
    merged = geometry_ops.safe_unary_union([box(0, 0, 5, 10), box(5, 0, 10, 10)])
    assert merged is not None
    assert merged.area == pytest.approx(100.0)


def test_safe_unary_union_of_empty_list():
    merged = safe_unary_union([])
    assert isinstance(merged, GeometryCollection)
    assert merged.is_empty


class _UnrepairableGeometry:
    """Stand-in for a geometry whose repair attempts all fail."""

    is_empty = False
    is_valid = False

    def buffer(self, _distance):
        raise ValueError("simulated buffer failure")


class _UndifferenceableGeometry:
    """Valid-looking geometry whose boolean ops always fail."""

    is_empty = False
    is_valid = True

    def difference(self, _other):
        raise ValueError("simulated difference failure")

    def union(self, _other):
        raise ValueError("simulated union failure")


def test_sanitize_geometry_falls_back_to_buffer_when_make_valid_fails(monkeypatch, bowtie):
    import diastasis.geometry_ops as geometry_ops

    def always_fails(_geometry):
        raise ValueError("simulated make_valid failure")

    monkeypatch.setattr(geometry_ops, "make_valid", always_fails)
    repaired = geometry_ops.sanitize_geometry(bowtie)
    # buffer(0) is the second repair strategy and resolves the self-intersection.
    assert repaired.is_valid


def test_sanitize_geometry_returns_original_when_every_repair_fails(monkeypatch):
    import diastasis.geometry_ops as geometry_ops

    def always_fails(_geometry):
        raise ValueError("simulated make_valid failure")

    monkeypatch.setattr(geometry_ops, "make_valid", always_fails)
    unrepairable = _UnrepairableGeometry()
    assert geometry_ops.sanitize_geometry(unrepairable) is unrepairable


def test_safe_difference_returns_geom_when_difference_always_fails():
    geom = _UndifferenceableGeometry()
    assert safe_difference(geom, box(0, 0, 1, 1)) is geom


def test_safe_unary_union_skips_members_that_cannot_be_unioned(monkeypatch):
    """A member whose union() raises is skipped, not fatal."""
    import diastasis.geometry_ops as geometry_ops

    def always_fails(_geometries):
        raise ValueError("simulated GEOS failure")

    monkeypatch.setattr(geometry_ops, "unary_union", always_fails)
    merged = geometry_ops.safe_unary_union(
        [box(0, 0, 10, 10), _UndifferenceableGeometry(), box(0, 0, 10, 10)]
    )
    assert merged is not None
    assert merged.area == pytest.approx(100.0)


def test_safe_unary_union_skips_none_members(monkeypatch):
    """A None member sanitizes to None and is skipped by the pairwise fold."""
    import diastasis.geometry_ops as geometry_ops

    def always_fails(_geometries):
        raise ValueError("simulated GEOS failure")

    monkeypatch.setattr(geometry_ops, "unary_union", always_fails)
    merged = geometry_ops.safe_unary_union([box(0, 0, 10, 10), None])
    assert merged is not None
    assert merged.area == pytest.approx(100.0)
