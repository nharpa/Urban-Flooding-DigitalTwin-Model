import argparse
from typing import Optional
from digital_twin.database.static_data_import import (
    load_spatial_data,
    import_spatial_catchments,
    create_design_rainfall_events,
    generate_spatial_risk_report,
)
from digital_twin.database.database_utils import FloodingDatabase
from digital_twin.spatial import spatial_data_processing


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover - thin wrapper
    print("Urban Flooding Digital Twin - Spatial Import Script")
    print("=" * 70)

    spatial_data_processing.main()

    try:
        db = FloodingDatabase()
    except Exception as exc:
        print(f"Failed to connect to MongoDB: {exc}")
        return 1

    try:
        catchments_data = load_spatial_data()
        print(f"  Loaded {len(catchments_data)} records")
    except FileNotFoundError:
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"  Failed to load spatial data: {exc}")
        return 1

    # 2. Import / upsert
    print("\nImporting / updating catchments...")
    imported, updated, skipped = import_spatial_catchments(catchments_data, db)
    print(f"  Imported: {imported}, Updated: {updated}, Skipped: {skipped}")

    # 3. Design rainfall events (optional)
    create_design_rainfall_events(db)
    print(f"  Created rainfall events")

    print("\nGenerating spatial risk report...")
    generate_spatial_risk_report(db)

    db.close()
    print("\nSpatial ingestion workflow complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
