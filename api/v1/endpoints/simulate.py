from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List
from dt.model import simulate_catchment

router = APIRouter()

class SimRequest(BaseModel):
    catchment_id: str = Field(..., examples=["perth_cbd_c1"])
    rain_mm_per_hr: List[float] = Field(..., min_items=1, examples=[[5,12,28,50,35,10]])
    timestamps_utc: List[str] = Field(..., min_items=1, examples=[["2025-09-15T00:00Z","2025-09-15T01:00Z"]])
    C: float = Field(..., ge=0, le=1, examples=[0.85])
    A_km2: float = Field(..., gt=0, examples=[1.4])
    Qcap_m3s: float = Field(..., gt=0, examples=[3.2])

@router.post("/simulate")
def simulate(req: SimRequest):
    result = simulate_catchment(
        req.rain_mm_per_hr,
        req.timestamps_utc,
        req.C,
        req.A_km2,
        req.Qcap_m3s,
    )
    return {"catchment_id": req.catchment_id, **result}
