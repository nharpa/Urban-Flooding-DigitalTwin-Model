"""Spatial utility helpers leveraging GeoPandas.

Provides point-in-polygon catchment lookup now that full geometry is stored.

Functions
---------
load_catchments_gdf(catchments: list[dict]) -> GeoDataFrame
    Build a GeoDataFrame from in-memory catchment records (each with a GeoJSON
    Polygon/MultiPolygon under ``geometry``).

find_catchment_for_point(catchments: list[dict], lon: float, lat: float) -> dict | None
    Return the single catchment whose geometry contains the given point. If
    multiple contain it, the smallest area (A_km2) is returned as a heuristic.

Dependencies: geopandas, shapely
"""
from __future__ import annotations

from typing import List, Dict, Optional
import geopandas as gpd
from shapely.geometry import shape, Point


def load_catchments_gdf(catchments: List[Dict]) -> gpd.GeoDataFrame:
    records = []
    for c in catchments:
        geom = c.get('geometry')
        if not geom:
            continue
        try:
            shp = shape(geom)
        except Exception:
            continue
        records.append({**c, 'geometry': shp})
    if not records:
        return gpd.GeoDataFrame(columns=['catchment_id', 'A_km2', 'geometry'], geometry='geometry', crs="EPSG:4326")
    return gpd.GeoDataFrame(records, geometry='geometry', crs="EPSG:4326")


def find_catchment_for_point(catchments: List[Dict], lon: float, lat: float) -> Optional[Dict]:
    """Return catchment dict whose polygon contains the lon/lat point.

    Parameters
    ----------
    catchments : list[dict]
        Catchment records including a GeoJSON geometry.
    lon, lat : float
        WGS84 coordinates.

    Returns
    -------
    dict | None
        Matching catchment or None if not found.
    """
    gdf = load_catchments_gdf(catchments)
    if gdf.empty:
        return None
    pt = Point(lon, lat)
    # Fast bbox pre-filter via GeoPandas spatial index if available
    try:
        possible = gdf[gdf.geometry.bounds.apply(lambda row: (
            row.minx <= lon <= row.maxx and row.miny <= lat <= row.maxy), axis=1)]
    except Exception:
        possible = gdf
    matches = possible[possible.contains(pt)]
    if matches.empty:
        return None
    # Choose smallest area (A_km2) to disambiguate nested polygons if any
    matches_sorted = matches.sort_values(
        by='A_km2') if 'A_km2' in matches.columns else matches
    # Return original dict (without shapely geometry object to keep JSON serialisable)
    record = matches_sorted.iloc[0].drop(labels=['geometry']).to_dict()
    # Preserve original GeoJSON geometry from source list (avoid shapely mapping to keep as-is)
    record['geometry'] = matches_sorted.iloc[0].geometry.__geo_interface__
    return record


__all__ = [
    'load_catchments_gdf', 'find_catchment_for_point'
]
