"""Weather API client for retrieving rainfall observations and creating events."""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os
import uuid
import pytz
import requests
from dotenv import load_dotenv

class WeatherAPIClient:
    """Wrapper for weather data retrieval + rainfall event conversion."""
    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None, default_lat: float = None, default_lon: float = None):
        load_dotenv()
        self.api_url = api_url or os.getenv("WEATHER_API_URL", "http://localhost:8000/api/v1/weather")
        self.api_token = api_token or os.getenv("WEATHER_API_TOKEN")
        if not self.api_token:
            raise ValueError("WEATHER_API_TOKEN not set. Provide via .env or constructor.")
        self.default_lat = default_lat if default_lat is not None else float(os.getenv("DEFAULT_LAT", -31.95))
        self.default_lon = default_lon if default_lon is not None else float(os.getenv("DEFAULT_LON", 115.86))
        self.perth_tz = pytz.timezone('Australia/Perth')

    def fetch_weather_data(self, lat: Optional[float] = None, lon: Optional[float] = None) -> Optional[Dict]:
        if lat is None:
            lat = self.default_lat
        if lon is None:
            lon = self.default_lon
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        data = {"lat": lat, "lon": lon}
        try:
            response = requests.post(self.api_url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch weather data: {e}")
            return None

    def extract_rainfall_series(self, weather_data: Dict) -> Tuple[List[float], List[str], Dict]:
        if not weather_data or "data" not in weather_data:
            return [], [], {}
        observations = weather_data["data"].get("observations", [])
        rain_mmhr = []; timestamps_utc = []; timestamps_local = []
        sorted_obs = sorted(observations, key=lambda x: x["local_date_time_full"])
        for obs in sorted_obs:
            rain_value = float(obs.get("rain_trace", "0.0"))
            rain_mmhr.append(rain_value * 2)
            time_str = obs["local_date_time_full"]
            dt_local = datetime.strptime(time_str, "%Y%m%d%H%M%S")
            dt_local_tz = self.perth_tz.localize(dt_local)
            dt_utc = dt_local_tz.astimezone(pytz.UTC)
            timestamps_utc.append(dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"))
            timestamps_local.append(dt_local.strftime("%Y-%m-%d %H:%M"))
        total_rainfall = sum(rain_mmhr) / 2
        peak_intensity = max(rain_mmhr) if rain_mmhr else 0
        duration_hours = len(rain_mmhr) * 0.5 if rain_mmhr else 0
        station_info = weather_data["data"].get("station_info", {})
        stats = {"total_rainfall_mm": round(total_rainfall, 2), "peak_intensity_mmhr": round(peak_intensity, 2), "duration_hours": duration_hours, "station_name": station_info.get("name", "Unknown"), "station_id": station_info.get("station_id", ""), "location": {"lat": station_info.get("lat", -31.95), "lon": station_info.get("lon", 115.86)}, "start_time_local": timestamps_local[0] if timestamps_local else "", "end_time_local": timestamps_local[-1] if timestamps_local else "", "observation_count": len(observations)}
        return rain_mmhr, timestamps_utc, stats

    def create_rainfall_event_from_api(self, weather_data: Dict, event_name: str = None, event_type: str = "historical") -> Dict:
        rain_mmhr, timestamps_utc, stats = self.extract_rainfall_series(weather_data)
        if not rain_mmhr:
            raise ValueError("No valid rainfall data found")
        event_id = f"weather_api_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        if not event_name:
            event_name = f"{stats['station_name']} - {stats['start_time_local']}"
        return {"event_id": event_id, "name": event_name, "rain_mmhr": rain_mmhr, "timestamps_utc": timestamps_utc, "event_type": event_type, "total_rainfall_mm": stats["total_rainfall_mm"], "peak_intensity_mmhr": stats["peak_intensity_mmhr"], "duration_hours": stats["duration_hours"], "source": f"Weather API - {stats['station_name']} ({stats['station_id']})", "metadata": {"station_info": stats, "api_fetch_time": datetime.utcnow().isoformat(), "observation_count": stats["observation_count"]}}

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
