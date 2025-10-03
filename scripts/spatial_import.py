import argparse
from typing import Optional
from digital_twin.database.static_data_import import (  # noqa: E402
    load_spatial_data,
    import_spatial_catchments,
    create_design_rainfall_events,
    run_risk_assessment,
    generate_spatial_risk_report,
)
from digital_twin.database.database_utils import FloodingDatabase  # noqa: E402


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Import spatial catchments JSON into MongoDB and optionally seed design events + run sample risk assessment.",
    )
    p.add_argument(
        "--file",
        default="data/catchments_spatial_matched.json",
        help="Path to spatial catchments JSON (default: %(default)s)",
    )
    p.add_argument(
        "--design-events/--no-design-events",
        dest="design_events",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Create (or recreate) design rainfall events after ingestion (default: enabled)",
    )
    p.add_argument(
        "--event",
        default="design_10yr",
        help="Rainfall event id to use for sample risk simulations (default: %(default)s)",
    )
    p.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of lowest-capacity catchments to sample for risk assessment (default: %(default)s)",
    )
    p.add_argument(
        "--skip-risk",
        action="store_true",
        help="Skip running the sample risk assessment & report generation.",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover - thin wrapper
    args = parse_args(argv)
    print("Urban Flooding Digital Twin - Spatial Import Script")
    print("=" * 70)
    try:
        db = FloodingDatabase()
    except Exception as exc:
        print(f"Failed to connect to MongoDB: {exc}")
        return 1

    # 1. Load spatial JSON
    print(f"\nLoading spatial data from: {args.file}")
    try:
        catchments_data = load_spatial_data(args.file)
        print(f"  Loaded {len(catchments_data)} records")
    except FileNotFoundError:
        print(f"  File not found: {args.file}")
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"  Failed to load spatial data: {exc}")
        return 1

    # 2. Import / upsert
    print("\nImporting / updating catchments...")
    imported, updated, skipped = import_spatial_catchments(catchments_data, db)
    print(f"  Imported: {imported}, Updated: {updated}, Skipped: {skipped}")

    # 3. Design rainfall events (optional)
    if args.design_events:
        print("\nCreating design rainfall events...")
        count = create_design_rainfall_events(db)
        print(f"  Created {count} events (idempotent)")
    else:
        print("\nSkipping design rainfall event creation (per flag)")

    # 4. Sample risk assessment (optional)
    if not args.skip_risk:
        print("\nRunning sample risk assessment simulations...")
        sim_count, high_risk = run_risk_assessment(
            db, num_samples=args.top, event_id=args.event
        )
        print(
            f"  Completed {sim_count} simulations; {high_risk} exceeded high-risk threshold"
        )
        print("\nGenerating spatial risk report...")
        generate_spatial_risk_report(db)
    else:
        print("\nSkipping risk assessment & report generation (per flag)")

    db.close()
    print("\nSpatial ingestion workflow complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
