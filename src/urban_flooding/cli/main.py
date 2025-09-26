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
from urban_flooding.domain.hydrology import q_runoff_m3s, risk_from_loading
from urban_flooding.domain.simulation import simulate_catchment


def _cmd_ingest_spatial(args: argparse.Namespace) -> int:
    db = FloodingDatabase()
    try:
        print(f"Loading spatial data file: {args.file}")
        data = load_spatial_data(args.file)
        imported, updated, skipped = import_spatial_catchments(data, db)
        print(f"Import summary: imported={imported} updated={updated} skipped={skipped}")
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
        system.continuous_monitoring(interval_minutes=args.interval, max_iterations=args.max_iterations)
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

    p_ingest = sub.add_parser("ingest-spatial", help="Import spatially matched catchments JSON into MongoDB")
    p_ingest.add_argument("--file", default="catchments_spatial_matched.json", help="Path to matched catchments JSON")
    p_ingest.add_argument("--design-events", action="store_true", help="Also create design rainfall events")
    p_ingest.set_defaults(func=_cmd_ingest_spatial)

    p_events = sub.add_parser("design-events", help="Create design & historical rainfall events only")
    p_events.set_defaults(func=_cmd_design_events)

    p_risk = sub.add_parser("risk-assess", help="Run comprehensive risk assessment for top catchments")
    p_risk.add_argument("--event", default="design_10yr", help="Rainfall event id to use")
    p_risk.add_argument("--top", type=int, default=20, help="Number of catchments to evaluate")
    p_risk.set_defaults(func=_cmd_risk_assess)

    p_rt = sub.add_parser("realtime-fetch", help="Fetch real-time weather and store as rainfall event")
    p_rt.set_defaults(func=_cmd_realtime_fetch)

    p_mon = sub.add_parser("monitor", help="Start (bounded) continuous monitoring loop")
    p_mon.add_argument("--interval", type=int, default=30, help="Interval minutes between cycles")
    p_mon.add_argument("--max-iterations", type=int, default=1, help="Run this many iterations (default 1 for safety)")
    p_mon.set_defaults(func=_cmd_monitor)

    p_tr = sub.add_parser("trends", help="Analyze historical rainfall + risk trends")
    p_tr.add_argument("--days", type=int, default=7, help="Look back this many days")
    p_tr.set_defaults(func=_cmd_trends)

    p_sim = sub.add_parser("simulate-simple", help="Pure hydrologic simulation (no DB)")
    p_sim.add_argument("--C", type=float, required=True, help="Runoff coefficient")
    p_sim.add_argument("--i", type=float, required=True, help="Rainfall intensity (mm/hr) for each step")
    p_sim.add_argument("--A", type=float, required=True, help="Area (km^2)")
    p_sim.add_argument("--capacity", type=float, required=True, help="Capacity Qcap (m^3/s)")
    p_sim.add_argument("--steps", type=int, default=5, help="Number of time steps")
    p_sim.set_defaults(func=_cmd_simulate_simple)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
