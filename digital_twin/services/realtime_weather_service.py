"""Weather API client for retrieving rainfall observations and creating events.

This module provides integration with external weather APIs to fetch real-time
rainfall observations and convert them into rainfall events suitable for flood
risk simulation. It handles API authentication, data extraction, and formatting
for compatibility with the digital twin's rainfall event schema.
"""

from datetime import datetime
from typing import Dict, Optional
import uuid
import requests
from digital_twin.auth.config import settings
from digital_twin.database.database_utils import FloodingDatabase


class WeatherAPIClient:
    """Client for external weather API integration.

    Provides methods to fetch real-time weather observations, extract rainfall
    data, and create rainfall events for flood risk assessment. Configured
    through environment variables for API URL and authentication tokens.

    Attributes
    ----------
    api_url : str
        Base URL for the weather API service.
    api_token : str
        Authentication token for weather API access.
    """

    def __init__(self):
        """Initialize weather API client with configuration from settings."""
        self.api_url = settings.WEATHER_API_URL
        self.api_token = settings.WEATHER_API_TOKEN

    def extract_rainfall_series(self, weather_data: Dict) -> Dict:
        """Extract and process rainfall time series from weather API response.

        Parses raw weather API data to extract rainfall intensities and timestamps,
        calculates summary statistics, and formats the data for use in flood
        risk simulations.

        Parameters
        ----------
        weather_data : Dict
            Raw response data from weather API containing historical observations.

        Returns
        -------
        Dict
            Processed rainfall data including time series, statistics, and metadata.
            Contains keys: total_rainfall_mm, peak_intensity_mmhr, duration_hours,
            start_time_local, end_time_local, rain_mmhr, timestamps_utc.
        """
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

    def craft_rainfall_event_from_api(self, weather_data: Dict, event_type: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Dict:
        """Create a rainfall event from weather API data.

        Processes weather API response data and formats it into a rainfall event
        document compatible with the digital twin's database schema. Generates
        unique event identifiers and metadata.

        Parameters
        ----------
        weather_data : Dict
            Raw weather API response containing rainfall observations.
        event_type : str
            Type classification for the rainfall event.
        lat : float, optional
            Latitude coordinate for event location metadata.
        lon : float, optional
            Longitude coordinate for event location metadata.

        Returns
        -------
        Dict
            Complete rainfall event document ready for database storage.
            Includes event_id, name, rainfall time series, and metadata.
        """
        stats = self.extract_rainfall_series(weather_data)
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
                "source": f"Weather API {event_type} - lat:{lat}, lon:{lon}"
                }

    def fetch_weather_observation_data(self, lat: Optional[float] = None, lon: Optional[float] = None) -> Optional[Dict]:
        headers = {"Authorization": f"Bearer {settings.WEATHER_API_TOKEN}",
                   "Content-Type": "application/json"}
        data = {"lat": lat, "lon": lon}
        try:
            if not settings.WEATHER_API_URL:
                print("Weather API URL is not set.")
                return None
            url = settings.WEATHER_API_URL + "/history"
            response = requests.post(
                url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            res = response.json()

            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch weather data: {e}")
            return None

    def create_rainfall_observations_event(self, lat: Optional[float] = None, lon: Optional[float] = None, catchment: Optional[dict] = None) -> Dict:

        weather_observations = self.fetch_weather_observation_data(lat, lon)

        if not weather_observations:
            raise ValueError("No weather observations available.")

        rainfall_event = self.craft_rainfall_event_from_api(
            weather_observations, "Observations", lat=lat, lon=lon)

        db = FloodingDatabase()
        db.save_rainfall_event(**rainfall_event)

        return rainfall_event["event_id"]

    def fetch_weather_forecast_data(self, lat: Optional[float] = None, lon: Optional[float] = None) -> Optional[Dict]:
        headers = {"Authorization": f"Bearer {settings.WEATHER_API_TOKEN}",
                   "Content-Type": "application/json"}
        data = {"lat": lat, "lon": lon}
        try:
            if not settings.WEATHER_API_URL:
                print("Weather API URL is not set.")
                return None
            url = settings.WEATHER_API_URL + "/forecast/hourly"
            response = requests.post(
                url, json=data, headers=headers, timeout=30)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch weather data: {e}")
            return None

    def create_rainfall_forecast_event(self, lat: Optional[float] = None, lon: Optional[float] = None, catchment: Optional[dict] = None) -> Dict:

        weather_observations = self.fetch_weather_observation_data(lat, lon)

        if not weather_observations:
            raise ValueError("No weather observations available.")

        rainfall_event = self.craft_rainfall_event_from_api(
            weather_observations, "Forecast", lat=lat, lon=lon)

        db = FloodingDatabase()

        db.save_rainfall_event(**rainfall_event)

        return rainfall_event["event_id"]
