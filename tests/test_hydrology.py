import pytest
from urban_flooding.domain.hydrology import q_runoff_m3s, risk_from_loading


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
