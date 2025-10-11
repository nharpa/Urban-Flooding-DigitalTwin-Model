# Real-time flood monitoring service for urban flooding digital twin.
# Provides weather ingestion, risk simulation, and alert reporting.

from typing import List, Dict, Optional
from datetime import datetime
import uuid

# Import project modules (assumes digital_twin/ is on PYTHONPATH)
from digital_twin.database.database_utils import FloodingDatabase
from digital_twin.services.risk_algorithm import simulate_catchment
from digital_twin.services.realtime_weather_service import WeatherAPIClient


class RealTimeFloodMonitor:

    def __init__(self, db: Optional[FloodingDatabase] = None):
        self.db = db if db else FloodingDatabase()
        self.weather_client = WeatherAPIClient()

    def start_periodic_monitoring(self, interval_seconds: int = 86400):
        """
        Starts a background process that runs every `interval_seconds` (default: 1 hour).
        For each catchment, creates a rainfall observation event using the centroid and runs risk assessment.
        Should be called on Uvicorn server startup.
        """
        import threading
        import time

        def monitor_loop():
            while True:
                print(
                    "[RealTimeFloodMonitor] Running periodic risk assessment for all catchments...")
                catchments = self.db.list_catchments()
                for catchment in catchments:
                    # Extract centroid (lat, lon) from catchment record
                    center = catchment.get("centroid", [None, None])
                    lat = center[0]
                    lon = center[1]
                    if lat is None or lon is None:
                        print(
                            f"[RealTimeFloodMonitor] Catchment {catchment.get('catchment_id')} missing centroid, skipping.")
                        continue
                    try:
                        event = self.weather_client.create_rainfall_observations_event(
                            lat=lat, lon=lon, catchment=catchment)
                        self.run_realtime_risk_assessment(
                            event, catchment["catchment_id"])
                        print(
                            f"[RealTimeFloodMonitor] Risk assessment complete for catchment {catchment.get('catchment_id')}")
                    except Exception as e:
                        print(
                            f"[RealTimeFloodMonitor] Error processing catchment {catchment.get('catchment_id')}: {e}")
                time.sleep(interval_seconds)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()

    def run_realtime_risk_assessment(self, rainfall_eventID: str, catchment_id: str) -> Dict:
        rainfall_event = self.db.get_rainfall_event(rainfall_eventID)
        if not rainfall_event:
            print(f"Rainfall event {rainfall_eventID} not found")
            return {}

        catchment = self.db.get_catchment(catchment_id)
        if not catchment:
            print(f"Catchment {catchment_id} not found")
            return {}

        # Simulate risk for this catchment
        sim_results = simulate_catchment(
            rain_mmhr=rainfall_event["rain_mmhr"],
            timestamps_utc=rainfall_event["timestamps_utc"],
            C=catchment["C"],
            A_km2=catchment["A_km2"],
            Qcap_m3s=catchment["Qcap_m3s"]
        )

        max_risk = sim_results["max_risk"]
        # Assign risk level category
        if max_risk >= 0.8:
            risk_level = "Very High"
        elif max_risk >= 0.6:
            risk_level = "High"
        elif max_risk >= 0.4:
            risk_level = "Medium"
        elif max_risk >= 0.2:
            risk_level = "Low"
        else:
            risk_level = "Very Low"
        # Find time of peak risk
        max_risk_time = None
        for i, point in enumerate(sim_results["series"]):
            if point["R"] == max_risk:
                max_risk_time = rainfall_event["timestamps_utc"][i]
                break
        # Save simulation result to DB
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
            notes=f"Real-time risk assessment - {risk_level} risk"
        )

        result = {
            "catchment_id": catchment["catchment_id"],
            "catchment_name": catchment["name"],
            "rainfall_event_id": rainfall_event["event_id"],
            "max_risk": max_risk,
            "risk_level": risk_level,
            "max_risk_time": max_risk_time,
            "alert": max_risk >= 0.6,
            "parameters": {
                "A_km2": catchment["A_km2"],
                "Qcap_m3s": catchment["Qcap_m3s"],
                "C": catchment["C"]
            }
        }
        return result

    def generate_alert_report(self, risk_results: List[Dict]) -> str:
        """
        Generate a formatted alert report string from risk assessment results.
        Includes summary statistics and up to 5 high-risk areas.
        """
        report = [
            "=" * 70,
            "Urban Flooding Real-time Warning/Alert Report",
            "=" * 70,
            f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        total = len(risk_results)
        high_risk = sum(1 for r in risk_results if r["max_risk"] >= 0.6)
        medium_risk = sum(1 for r in risk_results if 0.3 <=
                          r["max_risk"] < 0.6)
        low_risk = sum(1 for r in risk_results if r["max_risk"] < 0.3)
        report.extend([
            "[Risk Statistics]",
            f"Catchments evaluated: {total}",
            f"High risk areas: {high_risk}",
            f"Medium risk areas: {medium_risk}",
            f"Low risk areas: {low_risk}",
            ""
        ])
        alerts = [r for r in risk_results if r["alert"]]
        if alerts:
            report.append("[⚠️ Warning/Alert Areas]")
            for alert in alerts[:5]:
                report.extend([
                    f"\nArea: {alert['catchment_name']}",
                    f"  Risk value: {alert['max_risk']:.3f} ({alert['risk_level']})",
                    f"  Location: {alert['location'].get('center', {})}",
                    f"  Peak time: {alert['max_risk_time']}"
                ])
        else:
            report.extend([
                "[✓ No Warnings/Alerts]",
                "No high risk areas under current rainfall conditions"
            ])
        report.append("")
        report.append("=" * 70)
        return "\n".join(report)
