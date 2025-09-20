from math import exp
from typing import List, Dict


def q_runoff_m3s(C: float, i_mmhr: float, A_km2: float) -> float:
    return 0.278 * C * i_mmhr * A_km2

def risk_from_loading(L: float, k: float = 8.0) -> float:
    return 1.0 / (1.0 + exp(-k * (L - 1.0)))

def simulate_catchment(
    rain_mmhr: List[float],
    timestamps_utc: List[str],
    C: float,
    A_km2: float,
    Qcap_m3s: float,
) -> Dict:
    series = []
    max_r = 0.0
    for i, t in zip(rain_mmhr, timestamps_utc):
        Q = q_runoff_m3s(C, i, A_km2)
        L = Q / Qcap_m3s if Qcap_m3s > 0 else 1e6
        R = risk_from_loading(L)
        max_r = max(max_r, R)
        series.append({
            "t": t, "i": i,
            "Qrunoff": round(Q, 3),
            "L": round(L, 3),
            "R": round(R, 3)
        })
    return {"series": series, "max_risk": round(max_r, 3)}
