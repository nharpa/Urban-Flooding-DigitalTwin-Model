"""FastAPI endpoint for running a single catchment simulation.

This module exposes a POST /simulate route that accepts:
- A rainfall time series (mm/hr) aligned with ISO 8601 UTC timestamps
- Basic catchment properties (runoff coefficient C, area in km^2, and a
  downstream capacity in m^3/s)

The endpoint delegates the computation to `simulate_catchment` from the
domain model and returns the results along with the provided catchment_id.

Notes
-----
- `timestamps_utc` must be ISO 8601 strings with a trailing "Z" (UTC), e.g.
  "2025-09-15T00:00Z".
- The lengths of `rain_mm_per_hr` and `timestamps_utc` should match and be
  aligned; any validation beyond pydantic constraints is performed in
  downstream logic.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List
from src.urban_flooding.domain.simulation import simulate_catchment
from src.urban_flooding.auth.auth import verify_token

router = APIRouter()


class SimRequest(BaseModel):
    """Request body schema for the simulation endpoint.

    Attributes
    ----------
    catchment_id:
        Human-friendly identifier of the catchment/scenario being simulated.
    rain_mm_per_hr:
        Sequence of rainfall intensities in millimeters per hour (mm/hr).
        Must align one-to-one with `timestamps_utc`.
    timestamps_utc:
        ISO 8601 timestamps in UTC (suffix "Z"), e.g., "2025-09-15T00:00Z".
        Must align one-to-one with `rain_mm_per_hr`.
    C:
        Runoff coefficient (dimensionless) in the range [0, 1].
    A_km2:
        Catchment area in square kilometers (> 0).
    Qcap_m3s:
        Downstream capacity (capping flow) in cubic meters per second (> 0).
    """
    # Catchment / scenario identifier
    catchment_id: str = Field(..., examples=["perth_cbd_c1"])
    # Rainfall intensities [mm/hr]; length must match `timestamps_utc`
    rain_mm_per_hr: List[float] = Field(..., min_items=1, examples=[
                                        [5, 12, 28, 50, 35, 10]])
    # ISO 8601 UTC timestamps ("Z"); e.g., "2025-09-15T00:00Z"
    timestamps_utc: List[str] = Field(..., min_items=1, examples=[
                                      ["2025-09-15T00:00Z", "2025-09-15T01:00Z"]])
    # Runoff coefficient [0..1]
    C: float = Field(..., ge=0, le=1, examples=[0.85])
    # Catchment area [km^2]
    A_km2: float = Field(..., gt=0, examples=[1.4])
    # Downstream capacity [m^3/s]
    Qcap_m3s: float = Field(..., gt=0, examples=[3.2])


@router.post("/simulate")
def simulate(req: SimRequest, token: str = Depends(verify_token)):
    """Run a catchment simulation for the provided time series and properties.

    Parameters
    ----------
    req : SimRequest
        Parsed and validated request body containing rainfall series,
        timestamps, and catchment parameters.

    Returns
    -------
    dict
        JSON-serializable payload that includes the original `catchment_id`
        plus the key-value pairs returned by `simulate_catchment`.
    """
    # Delegate to domain model. Expected to return a dict-like result containing
    # computed series/metrics (e.g., discharge over time, peaks, etc.).
    result = simulate_catchment(
        req.rain_mm_per_hr,
        req.timestamps_utc,
        req.C,
        req.A_km2,
        req.Qcap_m3s,
    )
    return {"catchment_id": req.catchment_id, **result}
