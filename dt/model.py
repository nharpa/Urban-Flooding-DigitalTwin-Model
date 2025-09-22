"""Domain model utilities for the Urban Flooding Digital Twin.

This module provides small, composable functions used by the API layer to
compute runoff, capacity loading, and a simple risk proxy for a single
catchment over a time series.

Key functions
-------------
- q_runoff_m3s: Rational Method-like discharge estimate (m^3/s)
- risk_from_loading: Sigmoid mapping from capacity loading to risk [0..1]
- simulate_catchment: Vector-like loop that builds a result series
"""

from math import exp
from typing import List, Dict


def q_runoff_m3s(C: float, i_mmhr: float, A_km2: float) -> float:
    """Compute runoff/discharge using a Rational-Method style formula.

    Q = 0.278 * C * i * A

    where:
    - Q is discharge in m^3/s
    - C is the runoff coefficient [0..1]
    - i is rainfall intensity in mm/hr
    - A is catchment area in km^2

    Returns
    -------
    float
        Discharge in cubic meters per second (m^3/s).
    """
    return 0.278 * C * i_mmhr * A_km2

def risk_from_loading(L: float, k: float = 8.0) -> float:
    """Map capacity loading L to a risk score in [0, 1] via a sigmoid.

    Parameters
    ----------
    L : float
        Capacity loading ratio (Q / Qcap). Values > 1 imply exceedance.
    k : float, default 8.0
        Steepness parameter for the logistic curve.

    Returns
    -------
    float
        Risk proxy in [0, 1], close to 0 when L << 1 and near 1 when L >> 1.
    """
    return 1.0 / (1.0 + exp(-k * (L - 1.0)))

def simulate_catchment(
    rain_mmhr: List[float],
    timestamps_utc: List[str],
    C: float,
    A_km2: float,
    Qcap_m3s: float,
) -> Dict:
    """Simulate runoff and risk for a single catchment time series.

    Inputs must be aligned in time: `rain_mmhr[i]` corresponds to
    `timestamps_utc[i]`.

    Parameters
    ----------
    rain_mmhr : List[float]
        Rainfall intensities (mm/hr) per timestamp.
    timestamps_utc : List[str]
        ISO 8601 timestamps in UTC (with 'Z' suffix).
    C : float
        Runoff coefficient [0..1].
    A_km2 : float
        Catchment area in km^2 (> 0).
    Qcap_m3s : float
        Downstream capacity in m^3/s (> 0). If 0, set a very large loading.

    Returns
    -------
    Dict
        A JSON-serializable dictionary with:
        - "series": list of dicts for each timestamp containing:
            {"t": str, "i": float, "Qrunoff": float, "L": float, "R": float}
        - "max_risk": float, maximum risk across the series.
    """
    series = []
    max_r = 0.0
    for i, t in zip(rain_mmhr, timestamps_utc):
        # Compute runoff discharge (m^3/s) for this time step
        Q = q_runoff_m3s(C, i, A_km2)
        # Capacity loading ratio (dimensionless); if capacity is 0, set to a
        # very large number to represent certain exceedance.
        L = Q / Qcap_m3s if Qcap_m3s > 0 else 1e6
        # Map loading to a bounded risk proxy via sigmoid
        R = risk_from_loading(L)
        max_r = max(max_r, R)
        series.append({
            "t": t, "i": i,
            "Qrunoff": round(Q, 3),
            "L": round(L, 3),
            "R": round(R, 3)
        })
    return {"series": series, "max_risk": round(max_r, 3)}
