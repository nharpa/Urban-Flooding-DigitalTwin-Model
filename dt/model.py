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
    """
    Calculate runoff (Q) in cubic meters per second (m³/s).

    Formula:
        Q = 0.278 * C * i * A

    Parameters:
        C (float): Runoff coefficient (dimensionless, between 0 and 1).
        i_mmhr (float): Rainfall intensity (mm/hr).
        A_km2 (float): Catchment area (km²).

    Returns:
        float: Runoff in m³/s.
    """
    return 0.278 * C * i_mmhr * A_km2

def risk_from_loading(L: float, k: float = 8.0) -> float:
    """
    Calculate flood risk using a logistic function.

    Formula:
        R = 1 / (1 + exp(-k * (L - 1)))

    Parameters:
        L (float): Load factor (Q / Qcap).
        k (float): Steepness of the risk curve (default = 8.0).

    Returns:
        float: Risk value between 0 and 1.
    """
    return 1.0 / (1.0 + exp(-k * (L - 1.0)))

def simulate_catchment(
    rain_mmhr: List[float],
    timestamps_utc: List[str],
    C: float,
    A_km2: float,
    Qcap_m3s: float,
) -> Dict:
    """
    Simulate runoff and flood risk for a time series of rainfall.

    Parameters:
        rain_mmhr (List[float]): List of rainfall intensities (mm/hr).
        timestamps_utc (List[str]): List of timestamps (ISO 8601 format).
        C (float): Runoff coefficient.
        A_km2 (float): Catchment area (km²).
        Qcap_m3s (float): Drainage system capacity (m³/s).

    Returns:
        Dict:{
            A JSON-serializable dictionary with:
            - "series": list of dicts for each timestamp containing:
                {"t": str, "i": float, "Qrunoff": float, "L": float, "R": float}
            - "max_risk": float, maximum risk across the series.
        }
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

if __name__ == "__main__":
    # ========== Example 1: Single calculation ==========
    C = 0.6          # Runoff coefficient
    i_mmhr = 8       # Rainfall intensity (mm/hr)
    A_km2 = 10       # Catchment area (km²)
    Qcap_m3s = 100   # Capacity (m³/s)

    # Runoff calculation
    Q = q_runoff_m3s(C, i_mmhr, A_km2)

    # Load factor (Q relative to capacity)
    L = Q / Qcap_m3s

    # Risk value
    R = risk_from_loading(L)

    print("Runoff Q:", Q, "m³/s")
    print("Load L:", L)
    print("Risk R:", R)

    # ========== Example 2: Simulation over multiple hours ==========
    results = simulate_catchment(
        rain_mmhr=[5, 10, 20],   # Rainfall intensities
        timestamps_utc=["2025-09-22T00:00Z", "2025-09-22T01:00Z", "2025-09-22T02:00Z"],
        C=0.6,
        A_km2=10,
        Qcap_m3s=15
    )

    print("Simulation Results:")
    print(results)