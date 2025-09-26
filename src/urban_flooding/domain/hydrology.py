"""Hydrologic core formulas for Urban Flooding Digital Twin.

Contains pure computational utilities (no I/O) for runoff and risk.
"""
from math import exp

__all__ = ["q_runoff_m3s", "risk_from_loading"]

def q_runoff_m3s(C: float, i_mmhr: float, A_km2: float) -> float:
    """Rational Method discharge (m^3/s). Q = 0.278 * C * i * A."""
    return 0.278 * C * i_mmhr * A_km2

def risk_from_loading(L: float, k: float = 8.0) -> float:
    """Map loading ratio to logistic risk in [0,1]."""
    return 1.0 / (1.0 + exp(-k * (L - 1.0)))
