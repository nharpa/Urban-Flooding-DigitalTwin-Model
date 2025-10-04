"""Simulation utilities wrapping hydrologic formulas into time-series runs."""
import math
from typing import List, Dict


# -------------------- TUNING KNOBS --------------------
HEADROOM = 2.5          # aim for L ~ 1/HEADROOM at near-peak rain
CAP_BOOST_MAX = 50.0    # allow capacity boost up to 30x (was 3x)

# Optional: compress very large L before risk to avoid saturation
USE_LOG_COMPRESSION = True
L_LOG_RANGE = 40.0      # larger => more compression; 10–50 is a good start
# ------------------------------------------------------


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
    return 1.0 / (1.0 + math.exp(-k * (L - 1.0)))



def _compress_L_for_risk(L: float) -> float:
    """
    Map L >= 1 into a compressed range so the logistic risk stays responsive.
    Keeps L <= 1 unchanged; compresses only the 'excess' above 1.

    L_eff = 1 + log(1 + (L-1)) / log(1 + L_LOG_RANGE)

    - If L=1  => L_eff = 1
    - If L >> 1, L_eff grows slowly, so risk_from_loading won't be pinned at 1.0
    """
    if L <= 1.0:
        return L
    return 1.0 + math.log1p(L - 1.0) / math.log(1.0 + L_LOG_RANGE)


def simulate_catchment(
    rain_mmhr: List[float],
    timestamps_utc: List[str],
    C: float,
    A_km2: float,
    Qcap_m3s: float,
) -> Dict:
    """
    Simulate runoff and flood risk for a rainfall intensity time series.

    Returns:
        {
          "series": [{"t","i","Qrunoff","L","R"}, ...],
          "max_risk": float
        }
    """
    series: list = []
    max_r = 0.0

    # --------- Adaptive capacity (with cap) ---------
    if rain_mmhr:
        i_target = max(rain_mmhr) * 1.0           # near-peak rain
    else:
        i_target = 2.0

    Q_target = q_runoff_m3s(C, i_target, A_km2)     # flow at near-peak
    scale = 1.0

    if Qcap_m3s > 0 and Q_target > 0:
        required = Q_target / (Qcap_m3s * HEADROOM)
        if required > 1.0:
            # IMPORTANT: cap the boost so catchment differences survive,
            # but allow *enough* boost so we don't always saturate.
            scale = min(required, CAP_BOOST_MAX)

    Qcap_used = max(Qcap_m3s * scale, 1e-6)         # avoid div-by-zero

    # --------------- Time stepping ------------------
    for i, t in zip(rain_mmhr, timestamps_utc):
        Q = q_runoff_m3s(C, i, A_km2)
        L = Q / Qcap_used

        if USE_LOG_COMPRESSION:
            L_for_risk = _compress_L_for_risk(L)
        else:
            L_for_risk = L

        R = risk_from_loading(L_for_risk, k=3.0)
        max_r = max(max_r, R)

        series.append({
            "t": t,
            "i": i,
            "Qrunoff": round(Q, 3),
            "L": round(L, 3),             # raw load (helps debugging)
            "R": round(R, 3)              # displayed risk (post-compression if enabled)
        })

    return {"series": series, "max_risk": round(max_r, 3)}