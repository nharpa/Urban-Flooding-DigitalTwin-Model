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
from digital_twin.spatial.spatial_utils import find_catchment_for_point
from digital_twin.auth.auth import verify_token
from digital_twin.services.realtime_weather_service import WeatherAPIClient
from digital_twin.services.realtime_monitor import RealTimeFloodMonitor

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
    catchment_id: str  # Unique identifier for the catchment containing the point
    catchment_name: str  # Human-readable name of the catchment
    rainfall_event_id: str  # ID of the rainfall event used for the risk calculation
    # Maximum risk value computed for the catchment (0-1 scale)
    max_risk: float
    # Categorical risk level (e.g., Very Low, Low, Medium, High, Very High)
    risk_level: str
    # Model parameters used in the simulation (C, A_km2, Qcap_m3s)
    parameters: dict
    # Timestamp (UTC) when the maximum risk occurred
    max_risk_time: Optional[str]


@router.post("/risk/point", response_model=PointRiskResponse)
def risk_for_point(request: PointRiskRequest, token: str = Depends(verify_token)):

    db = FloodingDatabase()
    weather_client = WeatherAPIClient()
    monitor = RealTimeFloodMonitor(db=db)
    lon = float(request.lon)
    lat = float(request.lat)

    # Find catchment containing the point
    print(f"Computing risk for point ({lon}, {lat})")
    catchment = find_catchment_for_point(
        catchments=db.list_catchments(), lon=lon, lat=lat
    )
    # If no catchment found, return 404
    if not catchment:
        raise HTTPException(
            status_code=404, detail="No catchment found for point")

    if not request.rainfall_event_id:
        event_id = "design_2yr"
    elif request.rainfall_event_id == "current":
        event_id = weather_client.create_rainfall_observations_event(
            lat=lat, lon=lon, catchment=catchment)
    elif request.rainfall_event_id == "forecast":
        event_id = weather_client.create_rainfall_forecast_event(
            lat=lat, lon=lon, catchment=catchment)
    else:
        valid_event = db.get_rainfall_event(request.rainfall_event_id)
        if valid_event:
            event_id = request.rainfall_event_id
        else:
            event_id = "design_2yr"

    # Simulate risk for this catchment
    simulation = monitor.run_realtime_risk_assessment(
        rainfall_eventID=event_id,
        catchment_id=catchment["catchment_id"]
    )
    # Check simulation result
    if not simulation:
        raise HTTPException(
            status_code=500, detail="Risk simulation failed")

    # Format response
    response = PointRiskResponse(
        catchment_id=simulation["catchment_id"],
        catchment_name=simulation["catchment_name"],
        rainfall_event_id=simulation["rainfall_event_id"],
        max_risk=simulation["max_risk"],
        risk_level=simulation["risk_level"],
        parameters=simulation["parameters"],
        max_risk_time=simulation["max_risk_time"],
    )

    return response
