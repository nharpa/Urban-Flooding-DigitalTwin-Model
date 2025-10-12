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

    # Catchment statistics
    catchment_area_km2: float  # Catchment area in square kilometers
    runoff_coefficient: float  # Runoff coefficient (C parameter)
    pipe_capacity_m3s: float  # Pipe capacity in cubic meters per second
    total_pipe_length_m: Optional[float]  # Total pipe length in meters
    # Maximum pipe diameter in millimeters
    max_pipe_diameter_mm: Optional[float]
    pipe_count: Optional[int]  # Number of pipes in catchment
    flowcode: Optional[float]  # Flow code identifier
    catchment_centroid: Optional[list]  # Centroid coordinates [lat, lon]

    # Rainfall event data
    rainfall_event_name: Optional[str]  # Human-readable name of rainfall event
    # Description of the rainfall event
    rainfall_event_description: Optional[str]
    # Type (e.g., "design", "observed", "forecast")
    rainfall_event_type: Optional[str]
    # Duration of rainfall event in hours
    rainfall_duration_hours: Optional[float]
    total_rainfall_mm: Optional[float]  # Total rainfall amount in millimeters
    max_intensity_mmhr: Optional[float]  # Maximum rainfall intensity in mm/hr
    rainfall_timestamps: Optional[list]  # List of timestamps for rainfall data
    # List of rainfall intensities (mm/hr)
    rainfall_intensities: Optional[list]


@router.post("/risk/point", response_model=PointRiskResponse)
def risk_for_point(request: PointRiskRequest, token: str = Depends(verify_token)):
    """Assess flood risk for a specific geographic point.

    Finds the catchment containing the provided coordinates, retrieves or defaults
    to a rainfall event, runs flood risk simulation, and returns comprehensive
    risk assessment results including risk level categorization.

    Parameters
    ----------
    request : PointRiskRequest
        Geographic coordinates and optional rainfall event ID.
    token : str
        Bearer authentication token (dependency injected).

    Returns
    -------
    PointRiskResponse
        Comprehensive risk assessment including catchment info, risk metrics,
        rainfall data, and simulation parameters.

    Raises
    ------
    HTTPException
        404 if no catchment is found containing the specified point.
    """
    db = FloodingDatabase()
    weather_client = WeatherAPIClient()
    monitor = RealTimeFloodMonitor(db=db)
    lon = float(request.lon)
    lat = float(request.lat)

    # Find catchment containing the point
    print(f"FLOOD RISK ANALYSIS INITIATED for coordinates ({lon}, {lat})")
    print(
        f"Analyzing spatial data across {len(db.list_catchments())} catchment areas...")
    catchment = find_catchment_for_point(
        catchments=db.list_catchments(), lon=lon, lat=lat
    )

    if catchment:
        print(
            f"Target catchment identified: {catchment.get('name', 'Unknown')} (ID: {catchment.get('catchment_id')})")
        print(
            f"   Catchment specs: Area={catchment.get('A_km2', 0):.2f}km², Capacity={catchment.get('Qcap_m3s', 0):.1f}m³/s")

    if not catchment:
        raise HTTPException(
            status_code=404, detail="No catchment found for point")

    if not request.rainfall_event_id:
        event_id = "design_2yr"
    elif request.rainfall_event_id == "current":
        event_result = weather_client.create_rainfall_observations_event(
            lat=lat, lon=lon, catchment=catchment)
        if isinstance(event_result, str):
            event_id = event_result
        elif isinstance(event_result, dict):
            event_id = event_result.get("event_id", "design_2yr")
        else:
            event_id = "design_2yr"
    elif request.rainfall_event_id == "forecast":
        event_result = weather_client.create_rainfall_forecast_event(
            lat=lat, lon=lon, catchment=catchment)
        if isinstance(event_result, str):
            event_id = event_result
        elif isinstance(event_result, dict):
            event_id = event_result.get("event_id", "design_2yr")
        else:
            event_id = "design_2yr"
    else:
        valid_event = db.get_rainfall_event(request.rainfall_event_id)
        if valid_event:
            event_id = request.rainfall_event_id
        else:
            event_id = "design_2yr"

    # Get rainfall event data for response
    rainfall_event = db.get_rainfall_event(event_id)

    if rainfall_event:
        total_rain = sum(rainfall_event.get("rain_mmhr", []))
        max_intensity = max(rainfall_event.get("rain_mmhr", [0]))
        print(
            f"  RAINFALL EVENT: {rainfall_event.get('name', event_id)} - Total: {total_rain:.1f}mm, Peak: {max_intensity:.1f}mm/hr")

    print(f"Running hydrological simulation engine...")
    # Simulate risk for this catchment
    simulation = monitor.run_realtime_risk_assessment(
        rainfall_eventID=event_id,
        catchment_id=catchment["catchment_id"]
    )
    # Check simulation result
    if not simulation:
        raise HTTPException(
            status_code=500, detail="Risk simulation failed")

    print(
        f"RISK ASSESSMENT COMPLETE: {simulation['risk_level']} ({simulation['max_risk']:.3f})")

    # Format response with additional catchment and rainfall data
    response = PointRiskResponse(
        catchment_id=simulation["catchment_id"],
        catchment_name=simulation["catchment_name"],
        rainfall_event_id=simulation["rainfall_event_id"],
        max_risk=simulation["max_risk"],
        risk_level=simulation["risk_level"],
        parameters=simulation["parameters"],
        max_risk_time=simulation["max_risk_time"],

        # Catchment statistics
        catchment_area_km2=catchment.get("A_km2", 0.0),
        runoff_coefficient=catchment.get("C", 0.0),
        pipe_capacity_m3s=catchment.get("Qcap_m3s", 0.0),
        total_pipe_length_m=catchment.get("total_pipe_length_m"),
        max_pipe_diameter_mm=catchment.get("max_pipe_diameter_mm"),
        pipe_count=catchment.get("pipe_count"),
        flowcode=catchment.get("flowcode"),
        catchment_centroid=catchment.get("centroid"),

        # Rainfall event data
        rainfall_event_name=rainfall_event.get(
            "name") if rainfall_event else None,
        rainfall_event_description=rainfall_event.get(
            "description") if rainfall_event else None,
        rainfall_event_type=rainfall_event.get(
            "event_type") if rainfall_event else None,
        rainfall_duration_hours=rainfall_event.get(
            "duration_hours") if rainfall_event else None,
        total_rainfall_mm=sum(rainfall_event.get(
            "rain_mmhr", [])) if rainfall_event and rainfall_event.get("rain_mmhr") else None,
        max_intensity_mmhr=max(rainfall_event.get(
            "rain_mmhr", [])) if rainfall_event and rainfall_event.get("rain_mmhr") else None,
        rainfall_timestamps=rainfall_event.get(
            "timestamps_utc") if rainfall_event else None,
        rainfall_intensities=rainfall_event.get(
            "rain_mmhr") if rainfall_event else None,
    )

    return response
