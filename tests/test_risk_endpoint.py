from fastapi.testclient import TestClient
from main import create_app


class DummyDB:
    def __init__(self):
        self._catchments = [
            {
                "catchment_id": "test1",
                "name": "Test Catchment 1",
                "C": 0.6,
                "A_km2": 5.0,
                "Qcap_m3s": 10.0,
                "location": {
                    "bounds": {
                        "min_lon": 115.0,
                        "max_lon": 116.0,
                        "min_lat": -32.0,
                        "max_lat": -31.0,
                    }
                },
            }
        ]
        self._event = {
            "event_id": "design_10yr",
            "rain_mmhr": [5.0, 10.0, 15.0],
            "timestamps_utc": [
                "2025-09-25T00:00:00Z",
                "2025-09-25T01:00:00Z",
                "2025-09-25T02:00:00Z",
            ],
        }

    # Methods used by endpoint
    def list_catchments(self):
        return self._catchments

    def get_rainfall_event(self, event_id: str):
        if event_id == self._event["event_id"]:
            return self._event
        return None

    def list_rainfall_events(self, *args, **kwargs):
        return [self._event]


def test_point_risk_endpoint(monkeypatch):
    # Monkeypatch FloodingDatabase in the endpoint module to return dummy instance
    from api.v1.endpoints import risk as risk_module

    def _dummy_db():
        return DummyDB()

    monkeypatch.setattr(risk_module, "FloodingDatabase", lambda: _dummy_db())

    app = create_app()
    client = TestClient(app)
    payload = {"lon": 115.81, "lat": -31.87}
    resp = client.post("/api/v1/risk/point", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["catchment_id"] == "test1"
    assert 0.0 <= data["max_risk"] <= 1.0
    assert data["risk_level"] in {"very_low",
                                  "low", "medium", "high", "very_high"}


def test_point_risk_not_found(monkeypatch):
    from api.v1.endpoints import risk as risk_module

    class EmptyDB(DummyDB):
        def list_catchments(self):
            return []

    monkeypatch.setattr(risk_module, "FloodingDatabase", lambda: EmptyDB())
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/v1/risk/point",
                       json={"lon": 0, "lat": 0})
    assert resp.status_code == 404
