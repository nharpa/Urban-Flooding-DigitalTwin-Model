"""Spatial GeoJSON conversion & heuristic matching pipeline.

Migrated from legacy `geojson_converter_spatial.py`.
Provides functions to:
- Aggregate pipe network features
- Extract catchment polygon attributes
- Perform heuristic spatial matching (overlap / nearest / estimated)
- Save intermediate results
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import numpy as np

# ----------------------------- Pipe Hydraulics ----------------------------- #


def calculate_pipe_capacity(diameter_mm: float, slope: float, material: str = "RC") -> float:
    manning_n = {
        "RC": 0.013, "CP": 0.013, "VC": 0.011, "PVC": 0.010,
        "PE": 0.010, "HDPE": 0.010, "CI": 0.014, "STEEL": 0.012,
    }.get(material, 0.013)
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

# --------------------------- Geometry Utilities --------------------------- #


def get_polygon_bounds(geometry: Dict) -> Optional[Tuple[float, float, float, float]]:
    all_coords = []
    if geometry['type'] == 'Polygon':
        all_coords.extend(geometry['coordinates'][0])
    elif geometry['type'] == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            all_coords.extend(polygon[0])
    if not all_coords:
        return None
    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]
    return min(lons), min(lats), max(lons), max(lats)


def get_polygon_center(geometry: Dict) -> Optional[Tuple[float, float]]:
    bounds = get_polygon_bounds(geometry)
    if bounds:
        min_lon, min_lat, max_lon, max_lat = bounds
        return (min_lon + max_lon) / 2, (min_lat + max_lat) / 2
    return None


def get_polygon_area_km2(geometry: Dict) -> float:
    if geometry['type'] not in ['Polygon', 'MultiPolygon']:
        return 0

    def polygon_area(coords):
        if len(coords) < 3:
            return 0
        earth_radius_km = 6371.0
        area = 0.0
        for i in range(len(coords)):
            j = (i + 1) % len(coords)
            lat1, lon1 = coords[i][1], coords[i][0]
            lat2, lon2 = coords[j][1], coords[j][0]
            lat1 = math.radians(lat1)
            lat2 = math.radians(lat2)
            lon1 = math.radians(lon1)
            lon2 = math.radians(lon2)
            area += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
        return abs(area) * earth_radius_km * earth_radius_km / 2.0
    total_area = 0
    if geometry['type'] == 'Polygon':
        total_area = polygon_area(geometry['coordinates'][0])
    elif geometry['type'] == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            total_area += polygon_area(polygon[0])
    return total_area


def point_in_polygon(point: Tuple[float, float], polygon_bounds: Tuple[float, float, float, float]) -> bool:
    if not polygon_bounds:
        return False
    lon, lat = point
    min_lon, min_lat, max_lon, max_lat = polygon_bounds
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

# -------------------------- Aggregation Functions ------------------------- #


def aggregate_pipes_with_location(pipes_file: str) -> Dict[str, Dict]:
    with open(pipes_file, 'r') as f:
        pipes_data = json.load(f)
    subcatchment_data = defaultdict(lambda: {
        'pipes': [], 'all_coordinates': [],
        'bounds': {'min_lon': 180, 'min_lat': 90, 'max_lon': -180, 'max_lat': -90}
    })
    for feature in pipes_data['features']:
        props = feature['properties']
        geom = feature['geometry']
        subcatchment = props.get('SUBCATCHMENT', 'Unknown')
        diameter = props.get('DIAMETER', 0)
        length = props.get('PIPE_LENGTH', 0)
        grade = props.get('GRADE', 0)
        material = props.get('MATERIAL', 'RC')
        if diameter > 0 and length > 0:
            capacity = calculate_pipe_capacity(diameter, grade, material)
            coords = geom.get('coordinates', [])
            if coords:
                valid_coords = []
                for coord in coords:
                    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                        try:
                            lon = float(coord[0])
                            lat = float(coord[1])
                            valid_coords.append([lon, lat])
                        except (TypeError, ValueError):
                            continue
                if valid_coords:
                    subcatchment_data[subcatchment]['all_coordinates'].extend(
                        valid_coords)
                    for lon, lat in valid_coords:
                        bounds = subcatchment_data[subcatchment]['bounds']
                        bounds['min_lon'] = min(bounds['min_lon'], lon)
                        bounds['min_lat'] = min(bounds['min_lat'], lat)
                        bounds['max_lon'] = max(bounds['max_lon'], lon)
                        bounds['max_lat'] = max(bounds['max_lat'], lat)
            subcatchment_data[subcatchment]['pipes'].append({
                'diameter': diameter, 'length': length, 'capacity': capacity, 'material': material
            })
    subcatchment_results = {}
    for subcatch, data in subcatchment_data.items():
        pipes = data['pipes']
        if not pipes:
            continue
        total_length = sum(p['length'] for p in pipes)
        main_pipes = sorted(
            pipes, key=lambda x: x['diameter'], reverse=True)[:3]
        main_capacity = sum(p['capacity'] for p in main_pipes)
        bounds = data['bounds']
        center_lon = (bounds['min_lon'] + bounds['max_lon']) / 2
        center_lat = (bounds['min_lat'] + bounds['max_lat']) / 2
        subcatchment_results[subcatch] = {
            'pipe_count': len(pipes),
            'total_length_m': round(total_length, 2),
            'avg_diameter_mm': round(np.mean([p['diameter'] for p in pipes]), 0),
            'max_diameter_mm': max(p['diameter'] for p in pipes),
            'Qcap_m3s': round(main_capacity, 3),
            'bounds': {
                'min_lon': round(bounds['min_lon'], 6),
                'min_lat': round(bounds['min_lat'], 6),
                'max_lon': round(bounds['max_lon'], 6),
                'max_lat': round(bounds['max_lat'], 6)
            },
            'center': {'lon': round(center_lon, 6), 'lat': round(center_lat, 6)}
        }
    return subcatchment_results


def extract_catchments_with_geometry(catchments_file: str) -> Dict[str, Dict]:
    with open(catchments_file, 'r') as f:
        catchments_data = json.load(f)
    catchment_dict = {}
    for idx, feature in enumerate(catchments_data['features']):
        props = feature['properties']
        geom = feature['geometry']
        catch_name = props.get('catch_name', 'Unknown')
        unique_id = f"{catch_name}_{idx}"
        area_km2 = props.get('catch_norm', 0) or props.get('catch_full', 0)
        if area_km2 <= 0:
            area_km2 = get_polygon_area_km2(geom)
        bounds = get_polygon_bounds(geom)
        center = get_polygon_center(geom)
        if area_km2 > 0 and bounds:
            catchment_dict[unique_id] = {
                'name': catch_name,
                'sub_name': props.get('sub_name', ''),
                'A_km2': round(area_km2, 2),
                'basin_name': props.get('basin_name', ''),
                'type': props.get('type', ''),
                'management': props.get('management', ''),
                'bounds': {
                    'min_lon': round(bounds[0], 6), 'min_lat': round(bounds[1], 6),
                    'max_lon': round(bounds[2], 6), 'max_lat': round(bounds[3], 6)
                },
                'center': {'lon': round(center[0], 6), 'lat': round(center[1], 6)} if center else None
            }
    return catchment_dict

# ----------------------------- Matching Logic ------------------------------ #


def calculate_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return math.sqrt((lon2 - lon1)**2 + (lat2 - lat1)**2)


def spatial_match_catchments(subcatchment_pipes: Dict, catchment_areas: Dict, default_C: float = 0.6) -> List[Dict]:
    combined_catchments = []
    for subcatch_id, pipe_info in subcatchment_pipes.items():
        catchment_record = {
            'catchment_id': subcatch_id,
            'name': subcatch_id,
            'C': default_C,
            'Qcap_m3s': pipe_info['Qcap_m3s'],
            'pipe_count': pipe_info['pipe_count'],
            'total_pipe_length_m': pipe_info['total_length_m'],
            'max_pipe_diameter_mm': pipe_info['max_diameter_mm'],
            'location': {'center': pipe_info['center'], 'bounds': pipe_info['bounds']}
        }
        pipe_center = (pipe_info['center']['lon'], pipe_info['center']['lat'])
        best_match = None
        best_match_score = 0
        closest_distance = float('inf')
        closest_match = None
        for area_name, area_info in catchment_areas.items():
            area_center = area_info.get('center')
            if not area_center:
                continue
            distance = calculate_distance(
                pipe_center[0], pipe_center[1], area_center['lon'], area_center['lat'])
            if distance < closest_distance:
                closest_distance = distance
                closest_match = area_info
            area_bounds = (
                area_info['bounds']['min_lon'], area_info['bounds']['min_lat'],
                area_info['bounds']['max_lon'], area_info['bounds']['max_lat']
            )
            lon_overlap = min(pipe_info['bounds']['max_lon'], area_info['bounds']['max_lon']) - max(
                pipe_info['bounds']['min_lon'], area_info['bounds']['min_lon'])
            lat_overlap = min(pipe_info['bounds']['max_lat'], area_info['bounds']['max_lat']) - max(
                pipe_info['bounds']['min_lat'], area_info['bounds']['min_lat'])
            if lon_overlap > 0 and lat_overlap > 0:
                overlap_area = lon_overlap * lat_overlap
                pipe_area = (pipe_info['bounds']['max_lon'] - pipe_info['bounds']['min_lon']) * (
                    pipe_info['bounds']['max_lat'] - pipe_info['bounds']['min_lat'])
                if pipe_area > 0:
                    score = (overlap_area / pipe_area) * \
                        (1.0 / (1.0 + distance * 10))
                    if score > best_match_score:
                        best_match_score = score
                        best_match = area_info
            elif point_in_polygon(pipe_center, area_bounds):
                score = 1.0 / (1.0 + distance)
                if score > best_match_score:
                    best_match_score = score
                    best_match = area_info
        if best_match and best_match_score > 0.01:
            catchment_record['A_km2'] = best_match['A_km2']
            catchment_record['basin_name'] = best_match.get('basin_name', '')
            catchment_record['area_type'] = best_match.get('type', '')
            catchment_record['matched_catchment'] = best_match['name']
            catchment_record['match_score'] = round(best_match_score, 3)
            catchment_record['match_type'] = 'overlap'
            if 'Urban' in best_match.get('type', '') or 'urban' in best_match.get('management', '').lower():
                catchment_record['C'] = 0.8
            elif 'Residential' in best_match.get('type', ''):
                catchment_record['C'] = 0.6
            elif 'Rural' in best_match.get('type', '') or 'rural' in best_match.get('management', '').lower():
                catchment_record['C'] = 0.3
        elif closest_match and closest_distance < 0.1:
            catchment_record['A_km2'] = closest_match['A_km2']
            catchment_record['basin_name'] = closest_match.get(
                'basin_name', '')
            catchment_record['area_type'] = closest_match.get('type', '')
            catchment_record['matched_catchment'] = closest_match['name']
            catchment_record['match_distance_km'] = round(
                closest_distance * 111, 2)
            catchment_record['match_score'] = round(
                1.0 / (1.0 + closest_distance * 10), 3)
            catchment_record['match_type'] = 'nearest'
            catchment_record['area_confidence'] = 'low' if closest_distance > 0.05 else 'medium'
            if 'Coastal' in closest_match.get('type', '') or 'Swan' in closest_match.get('basin_name', ''):
                catchment_record['C'] = 0.7
            else:
                catchment_record['C'] = 0.6
        else:
            pipe_bounds = pipe_info['bounds']
            width_km = (pipe_bounds['max_lon'] -
                        pipe_bounds['min_lon']) * 111.0
            height_km = (pipe_bounds['max_lat'] -
                         pipe_bounds['min_lat']) * 111.0
            estimated_area = max(width_km * height_km * 1.5,
                                 pipe_info['total_length_m'] / 1000.0 * 0.5)
            catchment_record['A_km2'] = round(estimated_area, 2)
            catchment_record['area_estimated'] = True
            catchment_record['match_score'] = 0
        combined_catchments.append(catchment_record)
    return combined_catchments

# ----------------------------- Persistence -------------------------------- #


def save_results(data: List[Dict], output_file: str):
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
    pipes_file = data_dir / "INF_DRN_PIPES__PV_-8890311221817093938.geojson"
    catchments_file = data_dir / \
        "Hydrographic_Catchments_Subcatchments_DWER_030_WA_GDA2020_Public.geojson"
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
        print(f"     - Qcap: {info['Qcap_m3s']} m³/s")
        print(
            f"     - Center point: [{info['center']['lon']}, {info['center']['lat']}]")
        print("     - Boundary: [{:.4f}, {:.4f}] - [{:.4f}, {:.4f}]".format(
            info['bounds']['min_lon'], info['bounds']['min_lat'], info['bounds']['max_lon'], info['bounds']['max_lat']
        ))

    print("\n2. Processing catchment area geometry data...")
    catchment_areas = extract_catchments_with_geometry(str(catchments_file))
    print(
        f"   Found {len(catchment_areas)} catchment areas (total {len(catchment_areas)} with valid area)")

    print("\n3. Executing spatial matching...")
    matched_data = spatial_match_catchments(
        subcatchment_pipes, catchment_areas)
    print(f"   Created {len(matched_data)} matching records")

    print("\n4. Saving results...")
    save_results(matched_data, str(output_file))

    print("\n=== Conversion Statistics ===")
    print(f"Total catchment areas: {len(matched_data)}")
    overlap_count = sum(1 for c in matched_data if c.get(
        'match_type') == 'overlap')
    nearest_count = sum(1 for c in matched_data if c.get(
        'match_type') == 'nearest')
    estimated_count = sum(
        1 for c in matched_data if c.get('area_estimated', False))
    print(f"Overlap matching: {overlap_count}")
    print(f"Distance matching: {nearest_count}")
    print(f"Area estimation: {estimated_count}")
    if overlap_count + nearest_count > 0:
        match_scores = [c['match_score']
                        for c in matched_data if 'match_score' in c and c['match_score'] > 0]
        if match_scores:
            avg_score = np.mean(match_scores)
            max_score = np.max(match_scores)
            print(f"Average match score: {avg_score:.3f}")
            print(f"Highest match score: {max_score:.3f}")

    print("\nTop 5 matching results:")
    for i, record in enumerate(matched_data[:5]):
        print(f"\n{i+1}. {record['name']}:")
        print(f"   - Qcap: {record['Qcap_m3s']} m³/s")
        print(f"   - A_km2: {record['A_km2']} km²")
        print(
            f"   - Location: [{record['location']['center']['lon']:.4f}, {record['location']['center']['lat']:.4f}]")
        if 'matched_catchment' in record:
            match_type = record.get('match_type', 'unknown')
            if match_type == 'overlap':
                print(
                    f"   - Matched to: {record['matched_catchment']} (overlap match, score: {record['match_score']})")
            elif match_type == 'nearest':
                distance = record.get('match_distance_km', 'N/A')
                confidence = record.get('area_confidence', 'N/A')
                print(
                    f"   - Matched to: {record['matched_catchment']} (nearest match, distance: {distance}km, confidence: {confidence})")
        else:
            print("   - Not matched (area estimated)")
    return matched_data


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    'calculate_pipe_capacity', 'aggregate_pipes_with_location', 'extract_catchments_with_geometry',
    'spatial_match_catchments', 'save_results', 'main'
]
