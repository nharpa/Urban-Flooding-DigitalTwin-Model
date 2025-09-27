"""Simulation utilities wrapping hydrologic formulas into time-series runs."""
from typing import List, Dict
from .hydrology import q_runoff_m3s, risk_from_loading


def simulate_catchment(
    rain_mmhr: List[float],
    timestamps_utc: List[str],
    C: float,
    A_km2: float,
    Qcap_m3s: float,
) -> Dict:
    """Simulate runoff and flood risk for a rainfall intensity time series."""
    series = []
    max_r = 0.0
    for i, t in zip(rain_mmhr, timestamps_utc):
        Q = q_runoff_m3s(C, i, A_km2)
        L = Q / Qcap_m3s if Qcap_m3s > 0 else 1e6
        R = risk_from_loading(L)
        max_r = max(max_r, R)
        series.append({"t": t, "i": i, "Qrunoff": round(
            Q, 3), "L": round(L, 3), "R": round(R, 3)})
    return {"series": series, "max_risk": round(max_r, 3)}
