"""Spatial data import workflow utilities.

Migrated from legacy `import_spatial_to_mongodb.py`.
Provides functions for:
- Loading processed spatial catchment JSON
- Importing (upserting) catchments into the database
- Creating design rainfall events
- Running sampling risk assessments
- Generating spatial risk reports
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import List, Tuple, Sequence
from digital_twin.services.risk_simulation import simulate_catchment
from digital_twin.database.database_utils import FloodingDatabase


# ----------------------------- Data Loading -------------------------------- #

def load_spatial_data(json_file: str = "data/catchments_spatial_matched.json") -> list:
    with open(json_file, 'r') as f:
        return json.load(f)

# --------------------------- Catchment Import ------------------------------ #


def import_spatial_catchments(data: list, db: FloodingDatabase) -> Tuple[int, int, int]:
    imported_count = 0
    skipped_count = 0
    updated_count = 0
    for catchment in data:
        try:
            if 'C' in catchment:
                catchment['C'] = float(catchment['C'])
            if 'A_km2' in catchment:
                catchment['A_km2'] = float(catchment['A_km2'])
            if 'Qcap_m3s' in catchment:
                catchment['Qcap_m3s'] = float(catchment['Qcap_m3s'])
            if 'total_pipe_length_m' in catchment:
                catchment['total_pipe_length_m'] = float(
                    catchment['total_pipe_length_m'])
            if 'max_pipe_diameter_mm' in catchment:
                catchment['max_pipe_diameter_mm'] = float(
                    catchment['max_pipe_diameter_mm'])
            if 'pipe_count' in catchment:
                catchment['pipe_count'] = int(catchment['pipe_count'])
            # Geometry now preserved directly; ensure no accidental mutation beyond numeric casts
            if 'geometry' in catchment and catchment['geometry'] is None:
                # drop null geometry to keep docs clean
                catchment.pop('geometry')
            existing = db.get_catchment(catchment['catchment_id'])
            if existing:
                print(
                    f"Update: {catchment['catchment_id']} - {catchment.get('name')}")
                updated_count += 1
            else:
                print(
                    f"Import: {catchment['catchment_id']} - {catchment.get('name')}")
                imported_count += 1
            db.save_catchment_full(catchment)
        except Exception as e:  # pragma: no cover
            print(f"Error processing {catchment.get('catchment_id')}: {e}")
            skipped_count += 1
    return imported_count, updated_count, skipped_count

# -------------------------- Rainfall Event Seeding ------------------------- #


def create_design_rainfall_events(db: FloodingDatabase, events_file: str = "data/RainfallEvents.json") -> int:
    """Seed rainfall events from an external JSON file.

    Parameters
    ----------
    db : FloodingDatabase
        Database instance used for persistence.
    events_file : str, optional
        Path to JSON file containing a list of rainfall event objects.

    Returns
    -------
    int
        Number of events processed (attempted to save).
    """
    try:
        with open(events_file, 'r') as f:
            events: Sequence[dict] = json.load(f)
    except FileNotFoundError:
        print(f"Rainfall events file not found: {events_file}")
        return 0
    except json.JSONDecodeError as e:  # pragma: no cover - unlikely
        print(f"Invalid rainfall events JSON ({events_file}): {e}")
        return 0

    loaded_count = 0
    for raw in events:
        # Work on a shallow copy to avoid mutating list content externally
        event = dict(raw)
        try:
            if 'rain_mmhr' not in event or 'timestamps_utc' not in event:
                print(
                    f"Skipping invalid event (missing required fields): {event.get('event_id')}")
                continue
            event['rain_mmhr'] = [float(v) for v in event['rain_mmhr']]
            # Derived fields if absent
            event.setdefault('total_rainfall_mm',
                             float(sum(event['rain_mmhr'])))
            event.setdefault('peak_intensity_mmhr',
                             float(max(event['rain_mmhr'])))
            event.setdefault('duration_hours', float(len(event['rain_mmhr'])))
            db.save_rainfall_event(**event)
            print(
                f"Created rainfall event: {event.get('name', event.get('event_id'))}")
            loaded_count += 1
        except Exception as e:  # pragma: no cover
            print(
                f"Failed to create rainfall event {event.get('event_id')}: {e}")
    return loaded_count

# --------------------------- Risk Assessment ------------------------------- #


def run_risk_assessment(db: FloodingDatabase, num_samples: int = 10, event_id: str = "design_10yr"):
    catchments = db.list_catchments()
    catchments_sorted = sorted(
        catchments, key=lambda x: x.get('Qcap_m3s', float('inf')))
    selected = catchments_sorted[:num_samples]
    event = db.get_rainfall_event(event_id)
    if not event:
        print(f"Rainfall event not found: {event_id}")
        return 0, 0
    print(f"\nUsing rainfall event: {event['name']}")
    print(f"Running risk assessment for {len(selected)} catchments...")
    simulation_count = 0
    high_risk_count = 0
    for catchment in selected:
        results = simulate_catchment(
            rain_mmhr=event['rain_mmhr'],
            timestamps_utc=event['timestamps_utc'],
            C=catchment['C'],
            A_km2=catchment['A_km2'],
            Qcap_m3s=catchment['Qcap_m3s']
        )
        simulation_id = str(uuid.uuid4())
        db.save_simulation(
            simulation_id=simulation_id,
            catchment_id=catchment['catchment_id'],
            rain_mmhr=event['rain_mmhr'],
            timestamps_utc=event['timestamps_utc'],
            C=catchment['C'],
            A_km2=catchment['A_km2'],
            Qcap_m3s=catchment['Qcap_m3s'],
            series=results['series'],
            max_risk=results['max_risk'],
            rainfall_event_id=event['event_id'],
            notes=f"Risk assessment: {catchment['name']} - {event['name']}"
        )
        simulation_count += 1
        risk_level = "Low"
        if results['max_risk'] > 0.7:
            risk_level = "High"
            high_risk_count += 1
        elif results['max_risk'] > 0.3:
            risk_level = "Medium"
        print(
            f"  {catchment['name']}: risk={results['max_risk']:.3f} ({risk_level})")
        if 'location' in catchment and catchment['location']:
            center = catchment['location'].get('center', {})
            if center:
                print(
                    f"    Location: [{center.get('lon', 'N/A'):.4f}, {center.get('lat', 'N/A'):.4f}]")
    return simulation_count, high_risk_count

# --------------------------- Reporting Utilities --------------------------- #


def generate_spatial_risk_report(db: FloodingDatabase):
    print("\n" + "="*70)
    print("Urban Flooding Risk Spatial Analysis Report")
    print("="*70)
    stats = db.get_statistics_with_spatial()
    print("\n[Overall Statistics]")
    print(f"  Total catchments: {stats.get('total_catchments', 0)}")
    print(f"  Coverage area: {stats.get('total_area_km2', 0):.2f} km²")
    print(
        f"  Average drainage capacity: {stats.get('avg_capacity_m3s', 0):.3f} m³/s")
    print(
        f"  Total pipe network length: {stats.get('total_pipe_length_km', 0):.2f} km")
    print(f"  Total pipes: {stats.get('total_pipes', 0)}")
    print(f"  With location information: {stats.get('with_location', 0)}")
    print(f"  Estimated areas: {stats.get('estimated_areas', 0)}")
    high_risk_sims = db.get_high_risk_simulations(risk_threshold=0.5, limit=10)
    if high_risk_sims:
        print(f"\n[High Risk Areas] (risk value > 0.5)")
        print("-"*50)
        risk_by_catchment = {}
        for sim in high_risk_sims:
            risk_by_catchment.setdefault(
                sim['catchment_id'], []).append(sim['max_risk'])
        for cid, risks in list(risk_by_catchment.items())[:5]:
            catchment = db.get_catchment(cid)
            if catchment:
                avg_risk = sum(risks) / len(risks)
                max_risk = max(risks)
                print(f"\nCatchment area: {catchment['name']}")
                print(f"  Area: {catchment['A_km2']} km²")
                print(f"  Drainage capacity: {catchment['Qcap_m3s']} m³/s")
                print(f"  Runoff coefficient: {catchment['C']}")
                print(f"  Average risk: {avg_risk:.3f}")
                print(f"  Maximum risk: {max_risk:.3f}")
                if 'location' in catchment and catchment['location']:
                    center = catchment['location'].get('center', {})
                    if center:
                        print(
                            f"  Location: longitude={center.get('lon', 'N/A'):.4f}, latitude={center.get('lat', 'N/A'):.4f}")
                if 'pipe_count' in catchment:
                    print(f"  Pipe count: {catchment.get('pipe_count', 0)}")
                    print(
                        f"  Maximum pipe diameter: {catchment.get('max_pipe_diameter_mm', 0)} mm")
    print(f"\n[Capacity Distribution]")
    print("-"*50)
    capacity_ranges = [
        (0, 1, "Very small (< 1 m³/s)"),
        (1, 10, "Small (1-10 m³/s)"),
        (10, 50, "Medium (10-50 m³/s)"),
        (50, 100, "Large (50-100 m³/s)"),
        (100, float('inf'), "Very large (> 100 m³/s)")
    ]
    for min_cap, max_cap, label in capacity_ranges:
        count = len(db.get_catchments_by_capacity(
            min_cap, max_cap if max_cap != float('inf') else None))
        if count > 0:
            print(f"  {label}: {count} catchments")
    print("\n" + "="*70)

# ------------------------------- Workflow --------------------------------- #


def main():  # pragma: no cover
    print("Urban Flooding Digital Twin - Spatial Data Import Tool")
    print("="*70)
    print("\n1. Connecting to database...")
    db = FloodingDatabase()
    print("\n2. Loading spatially matched catchment area data...")
    try:
        catchments_data = load_spatial_data()
        print(f"   Loaded {len(catchments_data)} catchment area records")
    except FileNotFoundError:
        print("   Error: catchments_spatial_matched.json not found")
        print("   Please run geojson_converter_spatial.py first to generate data")
        return
    print("\n3. Importing catchment areas to MongoDB...")
    imported, updated, skipped = import_spatial_catchments(catchments_data, db)
    print(
        f"   New imports: {imported}, Updates: {updated}, Skipped: {skipped}")
    print("\n4. Creating design rainfall events...")
    event_count = create_design_rainfall_events(db)
    print(f"   Created {event_count} rainfall events")
    print("\n5. Running risk assessment simulations...")
    sim_count, high_risk = run_risk_assessment(
        db, num_samples=10, event_id="design_10yr")
    print(
        f"   Completed {sim_count} simulations, found {high_risk} high risk areas")
    print("\n6. Generating spatial risk analysis report...")
    generate_spatial_risk_report(db)
    print("\n7. Testing spatial query functionality...")
    print("   Finding catchments near Perth city center (115.857, -31.955)...")
    nearby = db.find_catchments_by_location(
        115.857, -31.955, max_distance_km=2)
    print(f"   Found {len(nearby)} catchments within 2km range")
    if nearby:
        print("   Top 3 catchments:")
        for c in nearby[:3]:
            print(f"     - {c['name']}: Qcap={c['Qcap_m3s']} m³/s")
    db.close()
    print("\nData import and analysis complete!")


__all__ = [
    'load_spatial_data', 'import_spatial_catchments', 'create_design_rainfall_events',
    'run_risk_assessment', 'generate_spatial_risk_report', 'main'
]

if __name__ == '__main__':  # pragma: no cover
    main()
