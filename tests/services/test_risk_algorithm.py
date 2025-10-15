import math
import pytest

from digital_twin.services.risk_algorithm import (
    q_runoff_m3s,
    risk_from_loading,
    _compress_L_for_risk,
    simulate_catchment,
)


def test_q_runoff_m3s_basic():
    # Example: C=0.8, i=25 mm/hr, A=1.5 km^2
    q = q_runoff_m3s(0.8, 25.0, 1.5)
    assert pytest.approx(q, rel=1e-6) == 0.278 * 0.8 * 25.0 * 1.5


def test_risk_from_loading_sigmoid_properties():
    # Below capacity ~ low risk
    r_low = risk_from_loading(0.2, k=8.0)
    # At capacity ~ 0.5 for symmetric logistic
    r_mid = risk_from_loading(1.0, k=8.0)
    # Above capacity ~ higher risk
    r_high = risk_from_loading(1.8, k=8.0)
    assert 0.0 < r_low < r_mid < r_high < 1.0
    assert math.isclose(r_mid, 0.5, rel_tol=0.0, abs_tol=1e-6)


def test_compress_L_for_risk_behavior():
    # At/below 1.0 unchanged
    assert _compress_L_for_risk(1.0) == 1.0
    assert _compress_L_for_risk(0.7) == 0.7
    # Much larger than 1 is compressed into a modest >1 value
    compressed = _compress_L_for_risk(20.0)
    assert 1.0 < compressed < 5.0


def test_simulate_catchment_structure_and_monotonicity():
    rain = [0.0, 5.0, 10.0, 20.0, 5.0]
    ts = [f"2025-01-01T0{i}:00Z" for i in range(len(rain))]
    out = simulate_catchment(rain, ts, C=0.7, A_km2=2.0, Qcap_m3s=3.0)

    assert set(out.keys()) == {"series", "max_risk"}
    assert len(out["series"]) == len(rain)
    for row in out["series"]:
        # Keys present
        assert set(row.keys()) == {"t", "i", "Qrunoff", "L", "R"}
        # Types and basic ranges
        assert isinstance(row["t"], str)
        assert row["i"] >= 0
        assert row["Qrunoff"] >= 0
        assert row["L"] >= 0
        assert 0.0 <= row["R"] <= 1.0

    # Max risk is scaled down in this implementation (0..0.1 typical)
    assert 0.0 <= out["max_risk"] <= 0.1

    # Verify that higher rainfall intensity yields non-decreasing instantaneous risk
    # around the increasing segments
    series = out["series"]
    assert series[0]["R"] <= series[1]["R"] <= series[2]["R"]
