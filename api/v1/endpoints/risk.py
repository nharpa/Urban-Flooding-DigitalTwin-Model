"""Risk assessment endpoints.

Provides an endpoint to compute the flood risk for the catchment that
contains (or whose bounding box contains) a provided geographic point.

Workflow:
1. Accept longitude/latitude + optional rainfall event id (defaults to latest or design_10yr)
2. Find candidate catchments whose bounding box encloses the point.
   (We currently only have stored center + bounds, not full polygons.)
3. Pick the smallest-area candidate (heuristic) if multiple.
4. Retrieve rainfall event (design_10yr fallback) and run simulation using
   stored C, A_km2, Qcap_m3s parameters.
5. Return risk metrics and basic catchment metadata.

If no catchment is found a 404 is returned.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.urban_flooding.persistence.database import FloodingDatabase
from src.urban_flooding.domain.simulation import simulate_catchment

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
        return "very_high"
    if value >= 0.6:
        return "high"
    if value >= 0.4:
        return "medium"
    if value >= 0.2:
        return "low"
    return "very_low"


def _select_catchment_for_point(lon: float, lat: float, catchments: list[dict]) -> dict:
    """Return the most appropriate catchment for a given point.

    Logic:
    1. Iterate through provided `catchments` and collect those whose location.bounds
       encloses the (lon, lat) point. Bounds must provide min/max for lon & lat.
    2. If multiple candidates are found, choose the one with the smallest `A_km2`
       (heuristic assuming tighter bounds more specific catchment).
    3. Raise HTTPException(404) if no candidates are found.

    Parameters
    ----------
    lon : float
        Longitude in WGS84.
    lat : float
        Latitude in WGS84.
    catchments : list[dict]
        Catchment records as returned by `FloodingDatabase.list_catchments()`.

    Returns
    -------
    dict
        Selected catchment dictionary.
    """
    candidates: list[dict] = []
    for c in catchments:
        loc = c.get("location") or {}
        bounds = (loc.get("bounds") or {}) if isinstance(loc, dict) else {}
        try:
            min_lon = bounds.get("min_lon")
            max_lon = bounds.get("max_lon")
            min_lat = bounds.get("min_lat")
            max_lat = bounds.get("max_lat")
            if None in (min_lon, max_lon, min_lat, max_lat):
                continue  # incomplete bounds, skip
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                candidates.append(c)
        except Exception:
            # Defensive: skip malformed catchment records
            continue
    if not candidates:

        raise HTTPException(
            status_code=404, detail="No catchment found for provided point")
    print(candidates)
    candidates.sort(key=lambda x: x.get("A_km2", float("inf")))
    print(
        f"Selected catchment {candidates[0]['catchment_id']} for point ({lon}, {lat})")
    return candidates[0]


@router.post("/risk/point", response_model=PointRiskResponse)
def risk_for_point(req: PointRiskRequest):
    db = FloodingDatabase()
    lon = float(req.lon)
    lat = float(req.lat)

    print(f"Computing risk for point ({lon}, {lat})")
    catchment = _select_catchment_for_point(
        lon=lon, lat=lat, catchments=db.list_catchments()
    )
    event_id = req.rainfall_event_id or "design_10yr"
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
    return PointRiskResponse(
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
