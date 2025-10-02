"""Command line interface for the Urban Flooding Digital Twin prototype.

Usage examples (from repository root):

  python -m urban_flooding.cli ingest-spatial --file data/catchments_spatial_matched.json
  python -m urban_flooding.cli design-events
  python -m urban_flooding.cli risk-assess --event design_10yr --top 25
  python -m urban_flooding.cli realtime-fetch
  python -m urban_flooding.cli monitor --interval 15 --max-iterations 2
  python -m urban_flooding.cli trends --days 14
  python -m urban_flooding.cli simulate-simple --C 0.85 --i 25 --A 0.75 --capacity 12

No external dependencies (argparse only) to keep runtime footprint minimal.
"""
from __future__ import annotations

import argparse
import sys
from typing import List

from urban_flooding.ingestion.spatial_import import (
    load_spatial_data,
    import_spatial_catchments,
    create_design_rainfall_events,
)
from urban_flooding.persistence.database import FloodingDatabase
from urban_flooding.services.integrated_system import IntegratedFloodSystem
from urban_flooding.domain.simulation import simulate_catchment

# ---------------- Issue Reports Command Handlers -----------------


def _cmd_init_db(_: argparse.Namespace) -> int:
    """Initialize MongoDB collections with schema validation and indexes.

    Safe to run multiple times: existing collections are modified (collMod) to
    ensure validators stay current. Provides a fast explicit setup step after
    bringing MongoDB online via docker-compose.
    """
    try:
        db = FloodingDatabase()
        # Touch the primary collections explicitly so that any lazy index
        # creation side-effects surface. The constructor already creates them.
        coll_names = [
            db.catchments.full_name,
            db.rainfall_events.full_name,
            db.simulations.full_name,
            db.issue_reports.full_name,
        ]
        print("Initialized MongoDB collections:")
        for name in coll_names:
            print(f" - {name}")
        db.close()
        return 0
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Database initialization failed: {exc}")
        return 1


def _cmd_issue_create(args: argparse.Namespace) -> int:
    db = FloodingDatabase()
    try:
        issue_id = db.create_issue_report(
            issue_type=args.type,
            description=args.description,
            latitude=args.lat,
            longitude=args.lon,
            user_uid=args.uid,
            display_name=args.display_name,
            email=args.email,
        )
        print(f"Created issue report: {issue_id}")
    finally:
        db.close()
    return 0


def _cmd_issue_list(args: argparse.Namespace) -> int:
    db = FloodingDatabase()
    try:
        reports = db.list_issue_reports(
            issue_type=args.type, user_uid=args.uid, limit=args.limit)
        if not reports:
            print("No issue reports found")
            return 0
        for r in reports:
            print(
                f"{r['issue_id']} | {r['issue_type']} | {r['created_at']}")
    finally:
        db.close()
    return 0


def _cmd_issue_near(args: argparse.Namespace) -> int:
    db = FloodingDatabase()
    try:
        reports = db.find_issue_reports_near(
            longitude=args.lon, latitude=args.lat, radius_meters=args.radius, limit=args.limit)
        for r in reports:
            coords = r['location']['coordinates']
            print(
                f"{r['issue_id']} @ ({coords[1]:.5f},{coords[0]:.5f}) {r['issue_type']}")
    finally:
        db.close()
    return 0


def _cmd_issue_stats(_: argparse.Namespace) -> int:
    db = FloodingDatabase()
    try:
        stats = db.issue_report_statistics()
        print(stats)
    finally:
        db.close()
    return 0


def _cmd_ingest_spatial(args: argparse.Namespace) -> int:
    db = FloodingDatabase()
    try:
        print(f"Loading spatial data file: {args.file}")
        data = load_spatial_data(args.file)
        imported, updated, skipped = import_spatial_catchments(data, db)
        print(
            f"Import summary: imported={imported} updated={updated} skipped={skipped}")
        if args.design_events:
            count = create_design_rainfall_events(db)
            print(f"Created {count} design/historical rainfall events")
    finally:
        db.close()
    return 0


def _cmd_design_events(_: argparse.Namespace) -> int:
    db = FloodingDatabase()
    try:
        count = create_design_rainfall_events(db)
        print(f"Created {count} rainfall events (design + historical)")
    finally:
        db.close()
    return 0


def _cmd_risk_assess(args: argparse.Namespace) -> int:
    system = IntegratedFloodSystem()
    try:
        results = system.run_comprehensive_risk_assessment(
            rainfall_event=None,
            use_realtime=False,
            event_id=args.event,
            top_n=args.top,
        )
        if not results:
            print("No results produced (check event id / database contents)")
            return 1
        dashboard = system.generate_alert_dashboard(results)
        print(dashboard)
    finally:
        system.close()
    return 0


def _cmd_realtime_fetch(_: argparse.Namespace) -> int:
    system = IntegratedFloodSystem()
    try:
        event = system.fetch_current_weather(save_to_db=True)
        if not event:
            return 1
        print(f"Stored real-time rainfall event: {event['event_id']}")
    finally:
        system.close()
    return 0


def _cmd_monitor(args: argparse.Namespace) -> int:
    system = IntegratedFloodSystem()
    try:
        system.continuous_monitoring(
            interval_minutes=args.interval, max_iterations=args.max_iterations)
    finally:
        system.close()
    return 0


def _cmd_trends(args: argparse.Namespace) -> int:
    system = IntegratedFloodSystem()
    try:
        system.analyze_historical_trends(days_back=args.days)
    finally:
        system.close()
    return 0


def _cmd_simulate_simple(args: argparse.Namespace) -> int:
    # Provide a minimal purely-computational simulation without DB dependency.
    rain_series = [args.i] * args.steps
    timestamps = [f"t{n}" for n in range(args.steps)]
    sim = simulate_catchment(
        rain_mmhr=rain_series,
        timestamps_utc=timestamps,
        C=args.C,
        A_km2=args.A,
        Qcap_m3s=args.capacity,
    )
    print("Runoff/Risk series:")
    for point in sim["series"]:
        print(point)
    print(f"Max risk: {sim['max_risk']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urban-flooding",
        description="Urban Flooding Digital Twin CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser(
        "ingest-spatial", help="Import spatially matched catchments JSON into MongoDB")
    p_ingest.add_argument("--file", default="catchments_spatial_matched.json",
                          help="Path to matched catchments JSON")
    p_ingest.add_argument("--design-events", action="store_true",
                          help="Also create design rainfall events")
    p_ingest.set_defaults(func=_cmd_ingest_spatial)

    p_events = sub.add_parser(
        "design-events", help="Create design & historical rainfall events only")
    p_events.set_defaults(func=_cmd_design_events)

    p_risk = sub.add_parser(
        "risk-assess", help="Run comprehensive risk assessment for top catchments")
    p_risk.add_argument("--event", default="design_10yr",
                        help="Rainfall event id to use")
    p_risk.add_argument("--top", type=int, default=20,
                        help="Number of catchments to evaluate")
    p_risk.set_defaults(func=_cmd_risk_assess)

    p_rt = sub.add_parser(
        "realtime-fetch", help="Fetch real-time weather and store as rainfall event")
    p_rt.set_defaults(func=_cmd_realtime_fetch)

    p_mon = sub.add_parser(
        "monitor", help="Start (bounded) continuous monitoring loop")
    p_mon.add_argument("--interval", type=int, default=30,
                       help="Interval minutes between cycles")
    p_mon.add_argument("--max-iterations", type=int, default=1,
                       help="Run this many iterations (default 1 for safety)")
    p_mon.set_defaults(func=_cmd_monitor)

    p_tr = sub.add_parser(
        "trends", help="Analyze historical rainfall + risk trends")
    p_tr.add_argument("--days", type=int, default=7,
                      help="Look back this many days")
    p_tr.set_defaults(func=_cmd_trends)

    p_sim = sub.add_parser(
        "simulate-simple", help="Pure hydrologic simulation (no DB)")
    p_sim.add_argument("--C", type=float, required=True,
                       help="Runoff coefficient")
    p_sim.add_argument("--i", type=float, required=True,
                       help="Rainfall intensity (mm/hr) for each step")
    p_sim.add_argument("--A", type=float, required=True, help="Area (km^2)")
    p_sim.add_argument("--capacity", type=float,
                       required=True, help="Capacity Qcap (m^3/s)")
    p_sim.add_argument("--steps", type=int, default=5,
                       help="Number of time steps")
    p_sim.set_defaults(func=_cmd_simulate_simple)

    p_init = sub.add_parser(
        "init-db", help="Create MongoDB collections & indexes (idempotent)")
    p_init.set_defaults(func=_cmd_init_db)

    # Issue reports group
    p_issue = sub.add_parser("issue-create", help="Create a new issue report")
    p_issue.add_argument("--type", required=True, help="Issue type string")
    p_issue.add_argument("--description", required=True,
                         help="Description text")
    p_issue.add_argument("--lat", type=float, required=True, help="Latitude")
    p_issue.add_argument("--lon", type=float, required=True, help="Longitude")
    p_issue.add_argument("--uid", required=True, help="Reporter user UID")
    p_issue.add_argument("--display-name", dest="display_name",
                         help="Reporter display name")
    p_issue.add_argument("--email", help="Reporter email")
    p_issue.add_argument("--photo", action="append",
                         help="Photo URL (repeatable)")
    p_issue.set_defaults(func=_cmd_issue_create)

    p_issue_list = sub.add_parser("issue-list", help="List issue reports")
    p_issue_list.add_argument("--type", help="Filter by issue type")
    p_issue_list.add_argument("--uid", help="Filter by reporting user UID")
    p_issue_list.add_argument("--limit", type=int, default=25)
    p_issue_list.set_defaults(func=_cmd_issue_list)

    p_issue_near = sub.add_parser(
        "issue-near", help="Find issue reports near a location")
    p_issue_near.add_argument("--lat", type=float, required=True)
    p_issue_near.add_argument("--lon", type=float, required=True)
    p_issue_near.add_argument("--radius", type=int,
                              default=1000, help="Radius meters")
    p_issue_near.add_argument("--limit", type=int, default=20)
    p_issue_near.set_defaults(func=_cmd_issue_near)

    p_issue_stats = sub.add_parser(
        "issue-stats", help="Show issue reporting statistics")
    p_issue_stats.set_defaults(func=_cmd_issue_stats)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
