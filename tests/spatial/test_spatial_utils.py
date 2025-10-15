import pytest

geopandas = pytest.importorskip("geopandas")
shapely = pytest.importorskip("shapely")

from digital_twin.spatial.spatial_utils import (
    calculate_pipe_grade,
    calculate_pipe_capacity,
    calculate_catchment_centroid,
    find_catchment_for_point,
)


def test_calculate_pipe_grade_typical_and_guards():
    # Typical positive grade
    assert calculate_pipe_grade(10.0, 9.0, 100.0) == pytest.approx(1.0)

    # Zero/negative computed grade coerced to nominal 0.1%
    assert calculate_pipe_grade(9.0, 10.0, 100.0) == 0.1

    # Too small or invalid lengths return None
    assert calculate_pipe_grade(10.0, 9.0, 0.0) is None
    assert calculate_pipe_grade(10.0, 9.0, 0.005) is None

    # Extremely large slopes capped at 50%
    assert calculate_pipe_grade(60.0, 0.0, 100.0) == 50.0


def test_calculate_pipe_capacity_material_and_slope_handling():
    # Provide materials mapping directly to avoid file I/O in tests
    materials = {"RC": 0.013, "PVC": 0.011}

    cap_rc = calculate_pipe_capacity(600.0, slope=1.0, material="RC", materials=materials)
    cap_pvc = calculate_pipe_capacity(600.0, slope=1.0, material="PVC", materials=materials)
    assert cap_rc > 0 and cap_pvc > 0
    # Lower Manning n => higher capacity
    assert cap_pvc > cap_rc

    # Sentinel/invalid slopes coerced to nominal positive slope
    cap_invalid = calculate_pipe_capacity(600.0, slope=-499.5, material="RC", materials=materials)
    assert cap_invalid > 0
    cap_none = calculate_pipe_capacity(600.0, slope=None, material="RC", materials=materials)
    assert cap_none > 0


def test_calculate_catchment_centroid_square():
    geom = {
        "type": "Polygon",
        "coordinates": [[
            [115.0, -32.0], [116.0, -32.0], [116.0, -31.0], [115.0, -31.0], [115.0, -32.0]
        ]],
    }
    lat, lon = calculate_catchment_centroid(geom)
    assert lat == pytest.approx(-31.5, rel=0, abs=1e-6)
    assert lon == pytest.approx(115.5, rel=0, abs=1e-6)


def test_find_catchment_for_point_contains_and_none():
    poly_a = {
        "type": "Polygon",
        "coordinates": [[
            [115.0, -32.0], [115.5, -32.0], [115.5, -31.5], [115.0, -31.5], [115.0, -32.0]
        ]],
    }
    poly_b = {
        "type": "Polygon",
        "coordinates": [[
            [115.4, -31.6], [116.0, -31.6], [116.0, -31.0], [115.4, -31.0], [115.4, -31.6]
        ]],
    }
    catchments = [
        {"catchment_id": "A", "A_km2": 1.0, "geometry": poly_a},
        {"catchment_id": "B", "A_km2": 2.0, "geometry": poly_b},
    ]

    # Point inside A
    rec = find_catchment_for_point(catchments, lon=115.25, lat=-31.75)
    assert rec
    assert rec["catchment_id"] == "A"

    # Point outside both
    rec2 = find_catchment_for_point(catchments, lon=114.0, lat=-30.0)
    assert rec2 is None
