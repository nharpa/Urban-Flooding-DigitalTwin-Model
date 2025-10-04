# Real-time flood monitoring service for urban flooding digital twin.
# Provides weather ingestion, risk simulation, and alert reporting.

from typing import List, Dict, Optional
from datetime import datetime
import uuid

# Import project modules (assumes digital_twin/ is on PYTHONPATH)
from digital_twin.database.database_utils import FloodingDatabase
from digital_twin.services.risk_algorithm import simulate_catchment
from digital_twin.services.fetch_realtime_weather import WeatherAPIClient


class RealTimeFloodMonitor:
    """
    Orchestrates real-time weather ingestion, risk simulation, and alert reporting.
    """

    def __init__(self, db: FloodingDatabase, weather_client: WeatherAPIClient):
        """
        Initialize the monitor with a database and weather API client.
        """
        self.db = db
        self.weather_client = weather_client

    def fetch_and_save_current_weather(self, lat: float = None, lon: float = None, save_to_db: bool = True) -> Optional[Dict]:
        """
        Fetch current weather data (optionally for a given lat/lon), convert to rainfall event, and optionally save to DB.
        Returns the rainfall event dict or None on failure.
        """
        weather_data = self.weather_client.fetch_weather_data(lat, lon)
        if not weather_data:
            return None
        try:
            rainfall_event = self.weather_client.create_rainfall_event_from_api(
                weather_data,
                event_name=f"Perth real-time observation - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                event_type="historical"
            )
            if save_to_db:
                self.db.save_rainfall_event(**rainfall_event)
                print(f"Saved rainfall event: {rainfall_event['event_id']}")
            return rainfall_event
        except Exception as e:
            print(f"Failed to process weather data: {e}")
            return None

    def run_realtime_risk_assessment(self, rainfall_event: Dict, catchment_ids: List[str] = None, risk_threshold: float = 0.5) -> List[Dict]:
        """
        Run risk assessment for a set of catchments using the provided rainfall event.
        If catchment_ids is None, defaults to 10 lowest-capacity catchments (max_capacity=50).
        Returns a list of risk result dicts (sorted by max_risk descending).
        """
        results = []
        if catchment_ids:
            # Fetch specified catchments
            catchments = [self.db.get_catchment(cid) for cid in catchment_ids]
            catchments = [c for c in catchments if c]
        else:
            # Default: sample 10 lowest-capacity catchments
            catchments = self.db.get_catchments_by_capacity(max_capacity=50)[
                :10]
        if not catchments:
            print("No catchments found to evaluate")
            return results
        print(
            f"\nRunning real-time risk assessment for {len(catchments)} catchments...")
        for catchment in catchments:
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
            result = {
                "catchment_id": catchment["catchment_id"],
                "catchment_name": catchment["name"],
                "location": catchment.get("location", {}),
                "max_risk": max_risk,
                "risk_level": risk_level,
                "max_risk_time": max_risk_time,
                "alert": max_risk >= risk_threshold,
                "details": {
                    "A_km2": catchment["A_km2"],
                    "Qcap_m3s": catchment["Qcap_m3s"],
                    "C": catchment["C"]
                }
            }
            results.append(result)
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
        # Sort results by risk descending
        results.sort(key=lambda x: x["max_risk"], reverse=True)
        return results

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
