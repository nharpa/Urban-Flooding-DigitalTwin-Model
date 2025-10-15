import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import simulate as simulate_endpoint
from digital_twin.auth.auth import verify_token


@pytest.fixture(scope="module")
def client():
    # Build a minimal app without the main.py lifespan to avoid DB usage
    app = FastAPI()
    # Include only the simulate router to avoid importing endpoints
    # that depend on DB or other heavy services during import.
    app.include_router(simulate_endpoint.router, prefix="/api/v1")

    # Override auth dependency to bypass token validation in tests
    app.dependency_overrides[verify_token] = lambda: "test-token"

    with TestClient(app) as c:
        yield c


def test_simulate_happy_path(client: TestClient):
    payload = {
        "catchment_id": "test_c1",
        "rain_mm_per_hr": [0, 10, 20, 10, 0],
        "timestamps_utc": [
            "2025-09-15T00:00Z",
            "2025-09-15T01:00Z",
            "2025-09-15T02:00Z",
            "2025-09-15T03:00Z",
            "2025-09-15T04:00Z",
        ],
        "C": 0.8,
        "A_km2": 1.2,
        "Qcap_m3s": 3.5,
    }

    headers = {"Authorization": "Bearer test-token"}
    resp = client.post("/api/v1/simulate", json=payload, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["catchment_id"] == "test_c1"
    assert "series" in body and "max_risk" in body
    assert len(body["series"]) == len(payload["rain_mm_per_hr"])
