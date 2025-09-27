"""High-level integrated system orchestration service.

This module encapsulates the former logic from `integrated_flood_system.py` and
exposes a service-style API for:
- Initial spatial/catchment data loading
- Real-time weather ingestion → rainfall event persistence
- Simulation & comprehensive risk assessment
- Alert dashboard generation
- Historical trend analysis
- Optional continuous monitoring loop

Dependences are injected (e.g. database, weather client) for easier testing.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid
import pytz

from urban_flooding.persistence.database import FloodingDatabase
from urban_flooding.domain.simulation import simulate_catchment
from urban_flooding.ingestion.weather_client import WeatherAPIClient

# Spatial / design rainfall utilities will be migrated next; to avoid a cyclic
# dependency we import lazily inside the method where needed.


class IntegratedFloodSystem:
    """Integrated urban flooding monitoring and alert system service."""

    def __init__(self, db: Optional[FloodingDatabase] = None, weather_client: Optional[WeatherAPIClient] = None):
        self.db = db or FloodingDatabase()
        self.weather_client = weather_client or WeatherAPIClient()
        self.perth_tz = pytz.timezone("Australia/Perth")

    # ------------------------- Initialization / Seeding --------------------- #
    def setup_initial_data(self) -> bool:
        from import_spatial_to_mongodb import (  # legacy module still shimmed
            load_spatial_data,
            import_spatial_catchments,
            create_design_rainfall_events,
        )
        print("\n" + "=" * 70)
        print("System Initialization")
        print("=" * 70)
        try:
            print("\n1. Importing spatially matched catchment area data...")
            catchments_data = load_spatial_data()
            imported, updated, skipped = import_spatial_catchments(
                catchments_data, self.db)
            print(
                f"   ✓ Import complete: Added/new {imported}, Updated {updated}, Skipped {skipped}")
        except FileNotFoundError:
            print("   ⚠️  Spatial data file not found")
            return False
        print("\n2. Creating design rainfall events...")
        event_count = create_design_rainfall_events(self.db)
        print(f"   ✓ Created {event_count} rainfall events")
        return True

    # --------------------------- Weather Ingestion -------------------------- #
    def fetch_current_weather(self, save_to_db: bool = True) -> Optional[Dict]:
        print("\nFetching real-time weather data...")
        weather_data = self.weather_client.fetch_weather_data()
        if not weather_data:
            print("   ❌ Unable to fetch weather data")
            return None
        try:
            rainfall_event = self.weather_client.create_rainfall_event_from_api(
                weather_data,
                event_name=f"Perth real-time observation - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                event_type="realtime",
            )
            if save_to_db:
                self.db.save_rainfall_event(**rainfall_event)
                print(
                    f"   ✓ Saved rainfall event: {rainfall_event['event_id']}")
            print(
                f"   Total rainfall: {rainfall_event['total_rainfall_mm']} mm")
            print(
                f"   Peak intensity: {rainfall_event['peak_intensity_mmhr']} mm/hr")
            print(f"   Duration: {rainfall_event['duration_hours']} hours")
            return rainfall_event
        except Exception as e:  # pragma: no cover - defensive
            print(f"   ❌ Failed to process weather data: {e}")
            return None

    # --------------------- Comprehensive Risk Assessment -------------------- #
    def run_comprehensive_risk_assessment(
        self,
        rainfall_event: Optional[Dict] = None,
        use_realtime: bool = True,
        event_id: Optional[str] = None,
        top_n: int = 20,
    ) -> List[Dict]:
        print("\n" + "=" * 70)
        print("Comprehensive Risk Assessment")
        print("=" * 70)
        if rainfall_event:
            print(f"Using provided rainfall event: {rainfall_event['name']}")
        elif use_realtime:
            print("Using real-time weather data...")
            rainfall_event = self.fetch_current_weather(save_to_db=True)
            if not rainfall_event:
                print("Unable to get real-time data, using historical event")
                event_id = event_id or "design_10yr"
        if not rainfall_event and event_id:
            rainfall_event = self.db.get_rainfall_event(event_id)
            if rainfall_event:
                print(f"Using historical event: {rainfall_event['name']}")
        if not rainfall_event:
            print("❌ No available rainfall events")
            return []
        print(
            f"\nSelecting top {top_n} potentially high-risk catchment areas...")
        all_catchments = self.db.list_catchments()
        for c in all_catchments:
            c["risk_score"] = (c["C"] * c["A_km2"]) / max(c["Qcap_m3s"], 0.1)
        catchments = sorted(
            all_catchments, key=lambda x: x["risk_score"], reverse=True)[:top_n]
        print(f"   Selected {len(catchments)} catchment areas for evaluation")
        results: List[Dict] = []
        print("\nRunning flooding simulations...")
        for i, catchment in enumerate(catchments, 1):
            sim_results = simulate_catchment(
                rain_mmhr=rainfall_event["rain_mmhr"],
                timestamps_utc=rainfall_event["timestamps_utc"],
                C=catchment["C"],
                A_km2=catchment["A_km2"],
                Qcap_m3s=catchment["Qcap_m3s"],
            )
            max_risk = sim_results["max_risk"]
            if max_risk >= 0.8:
                risk_level, risk_emoji = "Very High", "🔴"
            elif max_risk >= 0.6:
                risk_level, risk_emoji = "High", "🟠"
            elif max_risk >= 0.4:
                risk_level, risk_emoji = "Medium", "🟡"
            elif max_risk >= 0.2:
                risk_level, risk_emoji = "Low", "🟢"
            else:
                risk_level, risk_emoji = "Very Low", "⚪"
            max_risk_time = None
            max_risk_data = None
            for point in sim_results["series"]:
                if point["R"] == max_risk:
                    max_risk_time = point["t"]
                    max_risk_data = point
                    break
            result = {
                "catchment_id": catchment["catchment_id"],
                "catchment_name": catchment["name"],
                "location": catchment.get("location", {}),
                "max_risk": max_risk,
                "risk_level": risk_level,
                "risk_emoji": risk_emoji,
                "max_risk_time": max_risk_time,
                "max_risk_data": max_risk_data,
                "parameters": {
                    "C": catchment["C"],
                    "A_km2": catchment["A_km2"],
                    "Qcap_m3s": catchment["Qcap_m3s"],
                },
            }
            results.append(result)
            simulation_id = str(uuid.uuid4())
            self.db.save_simulation(
                simulation_id=simulation_id,
                catchment_id=catchment["catchment_id"],
                rain_mmhr=rainfall_event["rain_mmhr"],
                timestamps_utc=rainfall_event["timestamps_utc"],
                C=catchment["C"],
                A_km2=catchment["A_km2"],
                Qcap_m3s=catchment["Qcap_m3s"],
                series=sim_results["series"],
                max_risk=max_risk,
                rainfall_event_id=rainfall_event["event_id"],
                notes=f"Comprehensive risk assessment - {risk_level} risk",
            )
            if i % 5 == 0:
                print(f"   Completed {i}/{len(catchments)} catchment areas")
        results.sort(key=lambda x: x["max_risk"], reverse=True)
        print(
            f"\n✓ Completed risk assessment for {len(results)} catchment areas")
        return results

    # --------------------------- Alert Dashboard ---------------------------- #
    def generate_alert_dashboard(self, risk_results: List[Dict]) -> str:
        dashboard: List[str] = []
        dashboard.append("\n" + "=" * 70)
        dashboard.append("🚨 Urban Flooding Real-time Warning/Alert Dashboard")
        dashboard.append("=" * 70)
        dashboard.append(
            f"Generated at: {datetime.now(self.perth_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        dashboard.append("")
        total = len(risk_results)
        extreme_high = sum(1 for r in risk_results if r["max_risk"] >= 0.8)
        high = sum(1 for r in risk_results if 0.6 <= r["max_risk"] < 0.8)
        medium = sum(1 for r in risk_results if 0.4 <= r["max_risk"] < 0.6)
        low = sum(1 for r in risk_results if 0.2 <= r["max_risk"] < 0.4)
        very_low = sum(1 for r in risk_results if r["max_risk"] < 0.2)
        dashboard.append("[Risk Statistics]")
        dashboard.append(f"Total catchment areas evaluated: {total}")
        dashboard.append(f"🔴 Very High risk: {extreme_high}")
        dashboard.append(f"🟠 High risk: {high}")
        dashboard.append(f"🟡 Medium risk: {medium}")
        dashboard.append(f"🟢 Low risk: {low}")
        dashboard.append(f"⚪ Very Low risk: {very_low}")
        dashboard.append("")
        emergency_alerts = [r for r in risk_results if r["max_risk"] >= 0.8]
        if emergency_alerts:
            dashboard.append("[🚨 Emergency Warning/Alert Areas]")
            for alert in emergency_alerts[:5]:
                dashboard.append(
                    f"\n{alert['risk_emoji']} {alert['catchment_name']}")
                dashboard.append(f"   Risk value: {alert['max_risk']:.3f}")
                dashboard.append(
                    f"   Area: {alert['parameters']['A_km2']:.2f} km²")
                dashboard.append(
                    f"   Capacity: {alert['parameters']['Qcap_m3s']:.1f} m³/s")
                if alert['max_risk_data']:
                    dashboard.append(
                        f"   Peak load: {alert['max_risk_data']['L']:.1%}")
                    dashboard.append(
                        f"   Peak runoff: {alert['max_risk_data']['Qrunoff']:.1f} m³/s")
                if alert['location'] and alert['location'].get('center'):
                    center = alert['location']['center']
                    dashboard.append(
                        f"   Location: [{center.get('lon', 0):.4f}, {center.get('lat', 0):.4f}]"
                    )
        else:
            dashboard.append("[✓ No Emergency Warnings/Alerts]")
            dashboard.append("Currently no very high risk areas")
        high_risk_areas = [
            r for r in risk_results if 0.6 <= r["max_risk"] < 0.8]
        if high_risk_areas:
            dashboard.append("\n[⚠️ Key Focus Areas]")
            for area in high_risk_areas[:3]:
                dashboard.append(
                    f"{area['risk_emoji']} {area['catchment_name']}: risk value {area['max_risk']:.3f}"
                )
        dashboard.append("\n[Response Suggestions]")
        if extreme_high > 0:
            dashboard.append("❗ Immediate action:")
            dashboard.append("   - Activate emergency response plan")
            dashboard.append("   - Check drainage system operation status")
            dashboard.append("   - Prepare pumping equipment")
            dashboard.append("   - Notify relevant management departments")
        elif high > 0:
            dashboard.append("⚠️ Preventive measures:")
            dashboard.append("   - Strengthen drainage system monitoring")
            dashboard.append("   - Clean drainage pipelines")
            dashboard.append("   - Prepare emergency supplies")
        else:
            dashboard.append("✓ Routine monitoring:")
            dashboard.append("   - Maintain normal monitoring frequency")
            dashboard.append("   - Regular maintenance of drainage facilities")
        dashboard.append("")
        dashboard.append("=" * 70)
        return "\n".join(dashboard)

    # ------------------------ Continuous Monitoring Loop -------------------- #
    def continuous_monitoring(self, interval_minutes: int = 30, max_iterations: Optional[int] = None):
        print("\n" + "=" * 70)
        print("Starting Continuous Monitoring Mode")
        print("=" * 70)
        print(f"Monitoring interval: {interval_minutes} minutes")
        print("Press Ctrl+C to stop monitoring\n")
        iteration = 0
        try:
            while max_iterations is None or iteration < max_iterations:
                iteration += 1
                print(
                    f"\n[Iteration {iteration}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("-" * 50)
                rainfall_event = self.fetch_current_weather(save_to_db=True)
                if rainfall_event:
                    severity = self.weather_client.assess_rainfall_severity(
                        rainfall_event['total_rainfall_mm'],
                        rainfall_event['peak_intensity_mmhr'],
                    )
                    print(f"   Rainfall severity: {severity}")
                    if rainfall_event['peak_intensity_mmhr'] > 0:
                        print("   Rainfall detected, running risk assessment...")
                        risk_results = self.run_comprehensive_risk_assessment(
                            rainfall_event=rainfall_event,
                            top_n=10,
                        )
                        if risk_results:
                            high_risk_count = sum(
                                1 for r in risk_results if r['max_risk'] >= 0.6)
                            if high_risk_count > 0:
                                print(
                                    f"   ⚠️ Found {high_risk_count} high-risk areas!")
                                dashboard = self.generate_alert_dashboard(
                                    risk_results)
                                print(dashboard)
                    else:
                        print("   ✓ Currently no rainfall, system normal")
                else:
                    print("   ⚠️ Unable to fetch weather data")
                if max_iterations is None or iteration < max_iterations:
                    print(
                        f"\nWaiting {interval_minutes} minutes for next monitoring...")
                    import time
                    time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:  # pragma: no cover
            print("\n\nMonitoring stopped")
        except Exception as e:  # pragma: no cover
            print(f"\nError: {e}")

    # ----------------------------- Trend Analysis --------------------------- #
    def analyze_historical_trends(self, days_back: int = 7):
        print("\n" + "=" * 70)
        print(f"Historical Trend Analysis (past {days_back} days)")
        print("=" * 70)
        all_events = self.db.list_rainfall_events()
        recent_events: List[Dict] = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        for event in all_events:
            if "metadata" in event and "api_fetch_time" in event["metadata"]:
                try:
                    event_time = datetime.fromisoformat(
                        event["metadata"]["api_fetch_time"].replace(
                            "Z", "+00:00")
                    )
                    if event_time > cutoff_date:
                        recent_events.append(event)
                except Exception:
                    pass
        print(f"\nFound {len(recent_events)} recent rainfall events")
        if recent_events:
            total_rainfall = sum(e.get("total_rainfall_mm", 0)
                                 for e in recent_events)
            max_intensity = max((e.get("peak_intensity_mmhr", 0)
                                for e in recent_events), default=0)
            avg_rainfall = total_rainfall / \
                len(recent_events) if recent_events else 0
            print(f"Total cumulative rainfall: {total_rainfall:.1f} mm")
            print(f"Average rainfall: {avg_rainfall:.1f} mm")
            print(f"Maximum rainfall intensity: {max_intensity:.1f} mm/hr")
            recent_sims = self.db.get_simulations_by_date_range(days_back)
            if recent_sims:
                high_risk_sims = [
                    s for s in recent_sims if s["max_risk"] >= 0.6]
                print(f"\nRisk simulation statistics:")
                print(f"  Total simulations: {len(recent_sims)}")
                print(f"  High-risk events: {len(high_risk_sims)}")
                print(
                    f"  High-risk ratio: {len(high_risk_sims)/len(recent_sims)*100:.1f}%"
                )

    # ------------------------------- Teardown -------------------------------- #
    def close(self):
        self.db.close()
        print("\nSystem closed")


def demo():  # Minimal interactive demo replacement for legacy main()
    system = IntegratedFloodSystem()
    try:
        system.setup_initial_data()
        rainfall_event = system.fetch_current_weather(save_to_db=True)
        results = system.run_comprehensive_risk_assessment(
            rainfall_event=rainfall_event, top_n=10)
        if results:
            print(system.generate_alert_dashboard(results))
        system.analyze_historical_trends(days_back=7)
    finally:
        system.close()


__all__ = ["IntegratedFloodSystem", "demo"]
