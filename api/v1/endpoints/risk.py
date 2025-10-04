"""Risk assessment endpoints.

Provides an endpoint to compute the flood risk for the catchment that
contains (or whose bounding box contains) a provided geographic point.

Workflow:
1. Accept longitude/latitude + optional rainfall event id (defaults to latest or design_10yr)
2. Use polygon containment (geopandas) to find the catchment geometry containing the point.
3. If multiple contain, choose the smallest A_km2.
4. Retrieve rainfall event (design_10yr fallback) and run simulation using stored parameters.
5. Return risk metrics and metadata.

If no catchment is found a 404 is returned.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from digital_twin.database.database_utils import FloodingDatabase
from digital_twin.services.risk_algorithm import simulate_catchment
from digital_twin.spatial.spatial_utils import find_catchment_for_point
from digital_twin.auth.auth import verify_token
from digital_twin.services.fetch_realtime_weather import get_rainfall_event_from_api

router = APIRouter()


class PointRiskRequest(BaseModel):
    lon: float = Field(
        ..., ge=-180, le=180, description="Longitude in WGS84"
    )
    lat: float = Field(
        ..., ge=-90, le=90, description="Latitude in WGS84"
    )
    rainfall_event_id: Optional[str] = Field(
        None,
        description="Optional rainfall event id; defaults to 'design_10yr' if not provided",
    )


class PointRiskResponse(BaseModel):
    catchment_id: str
    catchment_name: str
    rainfall_event_id: str
    max_risk: float
    risk_level: str
    parameters: dict
    max_risk_time: Optional[str]
    max_risk_point: Optional[dict]


def _risk_level(value: float) -> str:
    if value >= 0.8:
        return "Very High"
    if value >= 0.6:
        return "High"
    if value >= 0.4:
        return "Medium"
    if value >= 0.2:
        return "Low"
    return "Very Low"


@router.post("/risk/point", response_model=PointRiskResponse)
def risk_for_point(request: PointRiskRequest, token: str = Depends(verify_token)):

    db = FloodingDatabase()
    lon = float(request.lon)
    lat = float(request.lat)

    print(f"Computing risk for point ({lon}, {lat})")
    catchment = find_catchment_for_point(
        catchments=db.list_catchments(), lon=lon, lat=lat
    )

    if request.rainfall_event_id == "current":
        # special case: fetch latest event
        print("Fetching current weather observation from API...")
        event_id = get_rainfall_event_from_api(
            lat=lat, lon=lon, catchment=catchment)
        event = db.get_rainfall_event(event_id)
    else:
        event_id = request.rainfall_event_id or "design_10yr"
        event = db.get_rainfall_event(event_id)

    if not event:
        # fallback: pick any existing event
        events = db.list_rainfall_events()
        if not events:
            raise HTTPException(
                status_code=500, detail="No rainfall events available")
        event = events[0]
        event_id = event["event_id"]
    sim = simulate_catchment(
        rain_mmhr=event["rain_mmhr"],
        timestamps_utc=event["timestamps_utc"],
        C=catchment["C"],
        A_km2=catchment["A_km2"],
        Qcap_m3s=catchment["Qcap_m3s"],
    )

    max_risk = sim["max_risk"]
    max_point = None
    max_time = None
    for p in sim["series"]:
        if p["R"] == max_risk:
            max_point = p
            max_time = p["t"]
            break

    response = PointRiskResponse(
        catchment_id=catchment["catchment_id"],
        catchment_name=catchment.get("name", catchment["catchment_id"]),
        rainfall_event_id=event_id,
        max_risk=max_risk,
        risk_level=_risk_level(max_risk),
        parameters={
            "C": catchment["C"],
            "A_km2": catchment["A_km2"],
            "Qcap_m3s": catchment["Qcap_m3s"],
        },
        max_risk_time=max_time,
        max_risk_point=max_point,
    )

    return response
