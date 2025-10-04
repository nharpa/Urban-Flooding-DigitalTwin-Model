"""Weather API client for retrieving rainfall observations and creating events."""
from datetime import datetime
from typing import Dict, Optional
import uuid
import requests
from digital_twin.auth.config import settings
from digital_twin.database.database_utils import FloodingDatabase


def fetch_weather_observation_data(lat: Optional[float] = None, lon: Optional[float] = None) -> Optional[Dict]:
    headers = {"Authorization": f"Bearer {settings.WEATHER_API_TOKEN}",
               "Content-Type": "application/json"}
    data = {"lat": lat, "lon": lon}
    try:
        response = requests.post(
            settings.WEATHER_API_URL, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        res = response.json()

        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch weather data: {e}")
        return None


def extract_rainfall_series(weather_data: Dict) -> Dict:
    if not weather_data or "data" not in weather_data:
        return {}

    observations = weather_data["data"].get("historyHours", [])
    rain_mmhr = []
    timestamps_local = []
    for obs in observations:
        rain_value = float(obs["precipitation"]
                           ["qpf"].get("quantity", "0.0"))
        rain_mmhr.append(rain_value)
        timestamps_local.append(obs["interval"]["endTime"])
    total_rainfall = sum(rain_mmhr)
    peak_intensity = max(rain_mmhr) if rain_mmhr else 0
    duration_hours = len(rain_mmhr) if rain_mmhr else 0
    rainfall_series = {"total_rainfall_mm": round(total_rainfall, 2),
                       "peak_intensity_mmhr": round(peak_intensity, 2),
                       "duration_hours": duration_hours,
                       "start_time_local": timestamps_local[0],
                       "end_time_local": timestamps_local[-1],
                       "rain_mmhr": rain_mmhr,
                       "timestamps_utc": timestamps_local}
    return rainfall_series


def create_rainfall_event_from_api(weather_data: Dict, lat: Optional[float] = None, lon: Optional[float] = None, catchment: Optional[dict] = None) -> Dict:
    stats = extract_rainfall_series(weather_data)
    event_id = f"weather_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    event_name = f"Real-time observation - {datetime.now().strftime('%Y-%m-%d %H:%M')} at ({lat}, {lon})"
    return {"event_id": event_id,
            "name": event_name,
            "rain_mmhr": stats.get("rain_mmhr", []),
            "timestamps_utc": stats.get("timestamps_utc", []),
            "total_rainfall_mm": stats["total_rainfall_mm"],
            "peak_intensity_mmhr": stats["peak_intensity_mmhr"],
            "event_type": "Real-time observation",
            "duration_hours": stats["duration_hours"],
            "location": {"lat": lat, "lon": lon},
            "source": f"Weather API - lat:{lat}, lon:{lon}"
            }


def get_rainfall_event_from_api(lat: Optional[float] = None, lon: Optional[float] = None, catchment: Optional[dict] = None) -> Dict:
    weather_observations = fetch_weather_observation_data(lat, lon)
    if not weather_observations:
        raise ValueError("No weather observations available.")
    rainfall_event = create_rainfall_event_from_api(
        weather_observations, lat=lat, lon=lon, catchment=catchment)
    db = FloodingDatabase()
    db.save_rainfall_event(**rainfall_event)
    return rainfall_event["event_id"]


def assess_rainfall_severity(self, total_mm: float, peak_intensity_mmhr: float) -> str:
    if peak_intensity_mmhr >= 50:
        return "extreme"
    if peak_intensity_mmhr >= 30:
        return "heavy"
    if peak_intensity_mmhr >= 10:
        return "moderate"
    if peak_intensity_mmhr >= 2:
        return "light"
    return "drizzle"
