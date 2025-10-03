import pytest
from digital_twin.services.risk_simulation import simulate_catchment, q_runoff_m3s, risk_from_loading


def test_simulate_catchment_increasing_intensity():
    rain = [1, 2, 3, 4]
    timestamps = [f"t{i}" for i in range(len(rain))]
    sim = simulate_catchment(
        rain_mmhr=rain, timestamps_utc=timestamps, C=0.8, A_km2=1.0, Qcap_m3s=5.0)
    assert 'series' in sim and 'max_risk' in sim
    assert len(sim['series']) == len(rain)
    # At least one risk value should be > 0
    assert any(p['R'] > 0 for p in sim['series'])


def test_simulate_catchment_zero_capacity_extreme_risk():
    rain = [5, 5, 5]
    timestamps = [f"t{i}" for i in range(len(rain))]
    sim = simulate_catchment(
        rain_mmhr=rain, timestamps_utc=timestamps, C=0.9, A_km2=1.2, Qcap_m3s=0.0)
    assert sim['max_risk'] > 0.99  # effectively saturated


def test_q_runoff_basic():
    # Q = 0.278 * C * i * A
    assert q_runoff_m3s(0.7, 20.0, 1.5) == pytest.approx(
        0.278 * 0.7 * 20.0 * 1.5)


def test_risk_midpoint():
    # L=1 should yield 0.5 exactly for logistic transform
    assert risk_from_loading(1.0) == pytest.approx(0.5, rel=1e-6)


def test_risk_growth():
    low = risk_from_loading(0.5)
    high = risk_from_loading(2.0)
    assert low < high
