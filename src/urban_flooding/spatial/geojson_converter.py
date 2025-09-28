"""Spatial GeoJSON conversion & heuristic matching pipeline.
"""


from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import numpy as np

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


# -------------------------- Aggregation Functions ------------------------- #

def aggregate_pipes_with_location(pipes_file: str) -> Dict[str, Dict]:
    """Aggregate pipe features by SUBCATCHMENT (hydraulic metrics only).

    Legacy spatial bounding box / centroid derivation has been removed because
    catchment mapping is already externally validated and full polygon
    geometry is now retained elsewhere. This function now focuses solely on
    hydraulic summarisation:
      * pipe_count
      * total_length_m
      * avg_diameter_mm
      * max_diameter_mm
      * Qcap_m3s  (sum of capacities of up to the three largest diameter pipes)

    Parameters
    ----------
    pipes_file : str
        Path to a GeoJSON-like file containing features with hydraulic
        attributes (diameter, length, invert levels, material).

    Returns
    -------
    Dict[str, Dict]
        Mapping of subcatchment id -> hydraulic summary metrics.
    """
    with open(pipes_file, 'r') as f:
        pipes_data = json.load(f)
    # Load material Manning values once for all pipes
    materials_lookup = load_pipe_materials()

    subcatchment_data = defaultdict(lambda: {'pipes': []})
    for feature in pipes_data['features']:
        # Defensive parsing of expected GeoJSON structure
        props = feature.get('properties', {})
        raw_ufi = props.get('ufi')
        # Normalise ufi to string to ensure consistent dictionary keys
        subcatchment = str(raw_ufi) if raw_ufi is not None else 'Unknown'

        # Extract key hydraulic attributes with fallbacks
        diameter = props.get('Feat_Diam') or 0
        length = props.get('Feat_Len') or 0
        inv_us = props.get('Inv_Lvl_US')
        inv_ds = props.get('Inv_Lvl_DS')

        # Derive pipe grade (percent); fallback to 0 if cannot be computed
        derived_grade = calculate_pipe_grade(inv_us, inv_ds, length)
        grade = derived_grade if derived_grade is not None else 0

        # Material code (for Manning n lookup)
        material = props.get('Feat_Mat', None)

        # Only consider pipes with valid diameter & length & material
        if diameter and length and diameter > 0 and length > 0 and material:
            capacity = calculate_pipe_capacity(
                diameter, grade, material, materials_lookup)
            subcatchment_data[subcatchment]['pipes'].append(
                {'diameter': diameter, 'length': length,
                    'capacity': capacity, 'material': material}
            )

    subcatchment_results = {}
    for subcatch, data in subcatchment_data.items():
        pipes = data['pipes']
        if not pipes:
            continue
        total_length = sum(p['length'] for p in pipes)
        # Consider the largest three pipes representative of effective capacity
        main_pipes = sorted(
            pipes, key=lambda x: x['diameter'], reverse=True)[:3]
        main_capacity = sum(p['capacity'] for p in main_pipes)
        subcatchment_results[subcatch] = {
            'pipe_count': len(pipes),
            'total_length_m': round(total_length, 2),
            'avg_diameter_mm': round(np.mean([p['diameter'] for p in pipes]), 0),
            'max_diameter_mm': max(p['diameter'] for p in pipes),
            'Qcap_m3s': round(main_capacity, 3),
        }
    return subcatchment_results


def extract_catchments_with_geometry(catchments_file: str) -> Dict[str, Dict]:
    """Load catchment features preserving full source geometry.

    Refactored: previously we reduced polygons to bounding boxes & centers.
    This caused loss of spatial fidelity for downstream calculations. We now
    retain the original GeoJSON ``geometry`` object so future processes can
    perform accurate spatial operations (e.g. point-in-polygon) without
    reloading source files.

    Behaviour changes:
    * ``bounds`` and ``center`` fields are no longer emitted here.
    * ``geometry`` is passed through verbatim (Polygon / MultiPolygon).
    * Only features with a positive numeric area attribute are kept (same
      filtering intent as before, but area now strictly attribute-driven).
    * Synthetic ids still generated when ``ufi`` absent.

    Parameters
    ----------
    catchments_file : str
        Path to the source catchments GeoJSON.

    Returns
    -------
    Dict[str, Dict]
        Mapping of id -> attributes incl. preserved ``geometry``.
    """
    with open(catchments_file, 'r') as f:
        catchments_data = json.load(f)
    catchment_dict: Dict[str, Dict] = {}
    for idx, feature in enumerate(catchments_data.get('features', [])):
        if not isinstance(feature, dict):
            continue
        props = feature.get('properties', {}) or {}
        geom = feature.get('geometry')
        if not geom or not isinstance(geom, dict) or 'type' not in geom:
            continue  # skip malformed
        catch_name = props.get('catch_name') or 'Unknown'
        ufi = props.get('ufi')
        key = str(ufi) if ufi is not None else f"{catch_name}_{idx}"
        area_km2 = props.get('catch_flod') or props.get('catch_full') or 0
        try:
            area_km2 = float(area_km2)
        except (TypeError, ValueError):
            area_km2 = 0.0
        if area_km2 <= 0:
            continue
        catchment_dict[key] = {
            'catchment_id': key,
            'ufi': ufi,
            'name': catch_name,
            'sub_name': props.get('sub_name', ''),
            'A_km2': round(area_km2, 2),
            'basin_name': props.get('basin_name', ''),
            'type': props.get('type', ''),
            'management': props.get('management', ''),
            'geometry': geom,
        }
    keyed_by_ufi = sum(1 for c in catchment_dict.values()
                       if c.get('ufi') is not None)
    print(
        f"Loaded {len(catchment_dict)} catchments ({keyed_by_ufi} with explicit ufi)")
    return catchment_dict


# --------------------------- Direct Join Logic ---------------------------- #


def join_pipes_catchments(subcatchment_pipes: Dict[str, Dict], catchment_areas: Dict[str, Dict], default_C: float = 0.6) -> List[Dict]:
    """Directly combine pipe aggregates with catchment geometry using shared 'ufi' key.

    Parameters
    ----------
    subcatchment_pipes : Dict
        Output of :func:`aggregate_pipes_with_location` keyed by ufi (or legacy id).
    catchment_areas : Dict
        Output of :func:`extract_catchments_with_geometry` keyed by ufi.
    default_C : float
        Baseline runoff coefficient when no heuristic adjustment applies.

    Returns
    -------
    List[Dict]
        Unified catchment records ready for persistence / simulation.
    """
    results: List[Dict] = []
    unmatched_pipes = []
    # Iterate over pipe aggregates first to ensure every pipe cluster tries to find a catchment
    for key, pipe_info in subcatchment_pipes.items():
        catchment = catchment_areas.get(key)
        if not catchment:
            unmatched_pipes.append(key)
            continue
        record = {
            'catchment_id': key,
            'name': catchment.get('name', key),
            'A_km2': catchment.get('A_km2'),
            'C': default_C,  # may adjust below
            'Qcap_m3s': pipe_info['Qcap_m3s'],
            'pipe_count': pipe_info['pipe_count'],
            'total_pipe_length_m': pipe_info['total_length_m'],
            'max_pipe_diameter_mm': pipe_info['max_diameter_mm'],
            'basin_name': catchment.get('basin_name', ''),
            'area_type': catchment.get('type', ''),
            'ufi': catchment.get('ufi'),
            # Preserve original polygon geometry for higher-accuracy spatial queries
            'geometry': catchment.get('geometry')
        }
        # Simple runoff coefficient heuristic based on area_type / management
        area_type = (catchment.get('type') or '').lower()
        management = (catchment.get('management') or '').lower()
        if 'urban' in area_type or 'urban' in management:
            record['C'] = 0.8
        elif 'residential' in area_type:
            record['C'] = 0.6
        elif 'industrial' in area_type:
            record['C'] = 0.75
        elif 'rural' in area_type or 'rural' in management or 'agri' in area_type:
            record['C'] = 0.3
        results.append(record)
    if unmatched_pipes:
        print(
            f"Warning: {len(unmatched_pipes)} pipe group(s) had no matching catchment ufi: {unmatched_pipes[:5]}{'...' if len(unmatched_pipes) > 5 else ''}")
    # Optionally, list catchments without pipes
    orphan_catchments = [
        k for k in catchment_areas.keys() if k not in subcatchment_pipes]
    if orphan_catchments:
        print(f"Info: {len(orphan_catchments)} catchment(s) lacked pipe data.")
    return results

# ----------------------------- Persistence -------------------------------- #


def save_results(data: List[Dict], output_file: str):
    """Persist results to JSON (UTF-8, pretty printed)."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data)} catchment area records to {output_file}")

# ----------------------------- CLI / Demo --------------------------------- #


def main():  # pragma: no cover - convenience script
    """Run full spatial conversion pipeline.

    Fixes applied:
    - Use the repository root /data directory for inputs & output
    - Output filename expected by user: catchment_spatial_matched.json (singular)
    - Add graceful error messages if source files are missing
    """
    # Determine project root as 3 levels up from this file ( .../urban_flooding_digitaltwin )
    project_root = Path(__file__).resolve().parents[3]
    data_dir = project_root / "data"
    pipes_file = data_dir / "PerthMetroStormDrainPipe.geojson"
    catchments_file = data_dir / \
        "PerthMetroCatchments.geojson"
    # User expectation (question) used singular form; keep legacy plural as fallback.
    output_file = data_dir / "catchments_spatial_matched.json"

    print("Starting GeoJSON conversion based on spatial location...")
    print(f"Data directory: {data_dir}")

    # Validate input existence
    missing = [p for p in [pipes_file, catchments_file] if not p.exists()]
    if missing:
        print("ERROR: Missing required input file(s):")
        for m in missing:
            print(f" - {m}")
        print("Aborting.")
        return []

    print("\n1. Processing drainage pipe network data...")
    subcatchment_pipes = aggregate_pipes_with_location(str(pipes_file))

    print(f"   Found {len(subcatchment_pipes)} subcatchment pipe networks")
    for i, (subcatch, info) in enumerate(list(subcatchment_pipes.items())[:3]):
        print(f"\n   Example {i+1}: {subcatch}")
        print(f"     - Number of pipes: {info['pipe_count']}")
        print(f"     - Qcap (top3 sum): {info['Qcap_m3s']} m³/s")
        print(f"     - Max diameter: {info['max_diameter_mm']} mm")

    print("\n2. Processing catchment area geometry data...")
    catchment_areas = extract_catchments_with_geometry(str(catchments_file))
    print(
        f"   Found {len(catchment_areas)} catchment areas (total {len(catchment_areas)} with valid area)")

    print("\n3. Joining pipe aggregates to catchments via foreign key 'ufi'...")
    matched_data = join_pipes_catchments(subcatchment_pipes, catchment_areas)
    print(f"   Created {len(matched_data)} joined catchment records")

    print("\n4. Saving results...")
    save_results(matched_data, str(output_file))

    print("\n=== Conversion Statistics ===")
    print(f"Total catchment areas: {len(matched_data)}")
    # Basic statistics
    total_capacity = sum(c.get('Qcap_m3s', 0) for c in matched_data)
    total_area = sum(c.get('A_km2', 0) for c in matched_data if c.get('A_km2'))
    print(f"Total joined capacity: {total_capacity:.2f} m³/s")
    print(f"Total represented area: {total_area:.2f} km²")

    print("\nTop 5 matching results:")
    if not matched_data:
        print(
            "No records to display – no matching foreign keys between pipes and catchments.")
    else:
        top = matched_data[:5]
        for i, record in enumerate(top):
            print(f"\n{i+1}. {record['name']} (ufi={record.get('ufi', '?')}):")
            print(f"   - Qcap: {record['Qcap_m3s']} m³/s")
            print(f"   - A_km2: {record.get('A_km2', 'N/A')} km²")
            center = record.get('location', {}).get('center', {})
            if center:
                print(
                    f"   - Location: [{center.get('lon', 'N/A')}, {center.get('lat', 'N/A')}]")
            print(f"   - C (runoff coefficient): {record.get('C')}")
    return matched_data


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    'load_pipe_materials', 'calculate_pipe_grade', 'calculate_pipe_capacity', 'aggregate_pipes_with_location',
    'extract_catchments_with_geometry', 'join_pipes_catchments', 'save_results', 'main'
]
