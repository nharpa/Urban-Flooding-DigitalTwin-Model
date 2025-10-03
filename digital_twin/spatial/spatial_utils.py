import math
import geopandas as gpd
import json
from typing import List, Dict, Optional
from shapely.geometry import shape, Point
from pathlib import Path


# ----------------------------- Pipe Hydraulics ----------------------------- #


def calculate_pipe_grade(inv_us: Optional[float], inv_ds: Optional[float], length_m: Optional[float]) -> Optional[float]:
    """Compute pipe grade (percent) from invert levels and length.

    Grade (%) = (Upstream Invert - Downstream Invert) / Length * 100

    Assumptions & Rules:
    * Positive grade implies flow from upstream (higher invert) to downstream (lower invert).
    * If any input is missing / non-numeric / length <= 0 -> return ``None`` (caller applies fallback).
    * Extremely small lengths (< 0.01 m) are treated as invalid to avoid division spikes.
    * Negative or zero computed grade is coerced to a small nominal positive slope (0.1%) when
      hydraulics require a slope (the capacity function later normalises). We still return the
      nominal value to keep downstream logic simple and explicit.

    Parameters
    ----------
    inv_us : float | None
        Upstream invert level (m AHD or local datum).
    inv_ds : float | None
        Downstream invert level (m AHD or local datum).
    length_m : float | None
        Pipe segment length in metres.

    Returns
    -------
    float | None
        Grade as a percentage (e.g. 1.5 => 1.5%), or ``None`` if cannot be derived.
    """
    try:
        if inv_us is None or inv_ds is None or length_m is None:
            return None
        length = float(length_m)
        if length <= 0.01:  # guard against division by tiny lengths
            return None
        rise = float(inv_us) - float(inv_ds)
        grade_pct = (rise / length) * 100.0
        # If grade is zero / negative, return a nominal minimal slope (0.1%)
        if grade_pct <= 0:
            return 0.1
        # Cap unrealistic large slopes (> 50%) which may indicate data issues
        if grade_pct > 50:
            return 50.0
        return grade_pct
    except (TypeError, ValueError):
        return None


DEFAULT_MANNING_N = 0.013
_PIPE_MANNING_CACHE: Dict[str, float] = {}


def load_pipe_materials(refresh: bool = False) -> Dict[str, float]:
    """Load pipe material Manning n values from ``data/PipeMaterials.json``.

    The JSON structure is expected to be ``{ code: { "manning_n": <number|null>, ... }, ... }``.
    Results are cached at module scope for efficiency. ``refresh=True`` forces a reload.

    Returns
    -------
    Dict[str, float]
        Mapping of material code -> Manning n (only codes with numeric values retained).
    """
    global _PIPE_MANNING_CACHE
    if _PIPE_MANNING_CACHE and not refresh:
        return _PIPE_MANNING_CACHE
    # Resolve repository root (same logic depth as main()) and locate data file
    project_root = Path(__file__).resolve().parents[3]
    materials_path = project_root / "data" / "PipeMaterials.json"
    mapping: Dict[str, float] = {}
    try:
        with open(materials_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for code, meta in raw.items():
            n_val = meta.get("manning_n")
            if isinstance(n_val, (int, float)) and n_val > 0:
                mapping[code.upper()] = float(n_val)
    except FileNotFoundError:
        # Silent fallback – function using this mapping will revert to DEFAULT_MANNING_N
        mapping = {}
    _PIPE_MANNING_CACHE = mapping
    return mapping


def calculate_pipe_capacity(diameter_mm: float, slope: float, material: str = "RC", materials: Optional[Dict[str, float]] = None) -> float:
    """Estimate pipe full-flow capacity (m^3/s) using simplified Manning formula.

    Parameters
    ----------
    diameter_mm : float
        Internal diameter of the pipe in millimetres.
    slope : float
        Longitudinal grade (percent). A sentinel / invalid slope (-499.5 or <= 0)
        is coerced to a nominal minimum (0.001) to avoid zero velocity.
    material : str, default "RC"
        Material code used to look up Manning roughness from ``PipeMaterials.json``.
    materials : Dict[str, float], optional
        Pre-loaded mapping of material codes to Manning n for efficiency. If not provided,
        the JSON file is loaded lazily & cached.

    Returns
    -------
    float
        Approximate discharge capacity in cubic metres per second.
    """
    if materials is None:
        materials = load_pipe_materials()
    manning_n = materials.get(material.upper(), DEFAULT_MANNING_N)
    diameter_m = diameter_mm / 1000.0
    radius_m = diameter_m / 2.0
    area = math.pi * radius_m ** 2
    wetted_perimeter = math.pi * diameter_m
    hydraulic_radius = area / wetted_perimeter
    if slope is None or slope <= 0 or slope == -499.5:
        slope = 0.001
    else:
        slope = abs(slope) / 100.0
    velocity = (1.0 / manning_n) * \
        (hydraulic_radius ** (2.0/3.0)) * (slope ** 0.5)
    return area * velocity


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
