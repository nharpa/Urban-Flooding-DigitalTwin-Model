# Urban Flooding Digital Twin (Spatial + Real-time Prototype)

This repository contains a prototype "digital twin" style workflow for urban flooding risk assessment. It integrates:

- Spatial processing of drainage pipe network GeoJSON and hydrographic catchment polygons
- Direct foreign key (ufi) join of pipe aggregates to catchment polygons (replaces legacy spatial heuristic matching)
- A lightweight hydrologic + capacity loading + sigmoid risk model (Rational Method inspired)
- MongoDB persistence with JSON Schema validation and indexes (catchments, rainfall events, simulations)
- Design storm & historical style rainfall event creation
- Real‑time weather API ingestion → rainfall event derivation → on‑demand & continuous risk simulation
- Reporting utilities (risk dashboards, alert summaries, trend analysis)

> Scope: This is a research / prototyping codebase, not a production-grade flood forecasting engine. It focuses on explainability, rapid iteration, and clear data flow.

---

## 1. Core Concepts

| Concept        | Description                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Catchment      | Spatial unit with area `A_km2`, runoff coefficient `C`, drainage capacity `Qcap_m3s`, and derived pipe statistics |
| Rainfall Event | Time series of intensities (mm/hr) + metadata; can be design, historical, realtime, forecast                      |
| Simulation     | Result of applying rainfall event to a catchment to compute runoff Q, load factor L=Q/Qcap, and risk R            |
| Risk Model     | Logistic transform of loading: `R = 1 / (1 + exp(-k (L - 1)))` (k default 8)                                      |

---

## 2. Repository Structure (Refactored src/ Layout)

```
├─ src/
│  └─ urban_flooding/
│     ├─ domain/                     # Pure hydrology + simulation logic
│     │  ├─ hydrology.py
│     │  └─ simulation.py
│     ├─ persistence/                # MongoDB adapter & schemas
│     │  ├─ database.py
│     │  └─ schemas.py
│     ├─ ingestion/                  # External data ingestion
│     │  ├─ weather_client.py        # Weather API → rainfall events
│     │  └─ spatial_import.py        # Catchment import & seeding utilities
│     ├─ services/                   # Higher-level orchestration
│     │  ├─ integrated_system.py
│     │  └─ realtime_monitor.py
│     ├─ spatial/                    # (Future) spatial processing utilities
│     ├─ cli/                        # Command line interface (argparse based)
│     │  └─ main.py
│     └─ __init__.py
├─ data/                             # GeoJSON inputs & derived JSON
├─ tests/                            # Pytest unit tests (hydrology & simulation)
├─ legacy shims *.py                 # Thin wrappers preserving old import paths
├─ requirements.txt
└─ README.md
```

Legacy top-level modules (e.g. `domain.py`, `database_v3.py`) remain as shims that re-export the refactored package to avoid breaking existing notebooks or scripts.

---

## 3. Data Flow Overview

1. Input GeoJSON files (pipes + catchment polygons) are processed by `geojson_converter_spatial.py`:

- Aggregates pipe segments per subcatchment (key = `ufi`) → capacity, length, diameter stats
- Extracts polygon bounds / centroid / area (or estimates if missing)
- Directly joins pipe aggregates to catchments using shared `ufi` (no overlap / nearest heuristic needed)
- Outputs `data/catchments_spatial_matched.json`

2. `import_spatial_to_mongodb.py` loads the JSON and upserts catchments into MongoDB with validation.
3. Design rainfall events are created (2, 10, 50, 100 year + historical template) and stored.
4. Simulations use `domain.simulate_catchment` to generate time series and risk metrics.
5. Real‑time weather API ingestion (`weather_api_client.py`) converts observations to a rainfall event.
6. `integrated_flood_system.py` can run comprehensive assessments, generate dashboards, and optionally loop in continuous monitoring mode.

---

## 4. MongoDB Schema Highlights

Collections:

- `catchments`: Hydraulic + spatial + matching metadata (center + bounding box) and pipe stats
- `rainfall_events`: Time series rainfall definitions
- `simulations`: Simulation outputs (series + max_risk + references)

Indexes (see `database_v3.py`):

- Functional: `catchment_id`, `simulation_id`, `event_id`
- Query support: capacity, name, risk, return period
- Spatial bounding box compound index (placeholder for future 2dsphere)

---

## 5. Risk & Hydrology Model

Runoff (Rational Method style):
`Q = 0.278 * C * i * A` (Q m³/s; C dimensionless; i mm/hr; A km²)

Capacity Loading: `L = Q / Qcap_m3s`

Risk (sigmoid): `R = 1 / (1 + exp(-k (L - 1)))` where `k` controls steepness (~8)

Interpretation (suggested thresholds):

- R < 0.2 → Very Low
- 0.2–0.4 → Low
- 0.4–0.6 → Medium
- 0.6–0.8 → High
- ≥ 0.8 → Very High (potential alert)

---

## 6. Setup & Installation

Prerequisites:

- Python 3.10+
- MongoDB running locally (default URI `mongodb://localhost:27017/`)

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

(Optional) Set environment variable for custom Mongo connection:

```powershell
$env:MONGODB_URI = "mongodb://user:pass@host:27017/?authSource=admin"
```

---

## 7. Typical Workflow (CLI First)

The new CLI consolidates common workflows. Run commands from the repository root (ensure `src` is on `PYTHONPATH`, which happens automatically when running from root).

List commands:

```powershell
python -m urban_flooding.cli -h
```

### A. Ingest Spatial Catchments + Seed Design Events

```powershell
python -m urban_flooding.cli ingest-spatial --file data/catchments_spatial_matched.json --design-events
```

### B. Create / Recreate Only Design Rainfall Events

```powershell
python -m urban_flooding.cli design-events
```

### C. Run Comprehensive Risk Assessment (Design Storm)

```powershell
python -m urban_flooding.cli risk-assess --event design_10yr --top 25
```

### D. Fetch Real-time Weather & Store Event

```powershell
python -m urban_flooding.cli realtime-fetch
```

### E. (Bounded) Continuous Monitoring Loop

```powershell
python -m urban_flooding.cli monitor --interval 15 --max-iterations 2
```

### F. Analyze Recent Trends

```powershell
python -m urban_flooding.cli trends --days 14
```

### G. Pure Hydrologic Quick Simulation (No DB)

```powershell
python -m urban_flooding.cli simulate-simple --C 0.8 --i 25 --A 1.2 --capacity 18 --steps 6
```

The legacy scripts (`import_spatial_to_mongodb.py`, `integrated_flood_system.py`, etc.) still work but are maintained as shims; prefer the CLI above.

### A. Generate Spatially Matched Catchments

```powershell
python geojson_converter_spatial.py
```

Outputs `catchments_spatial_matched.json` (default location: working directory or `data/`).

### B. Import Data & Seed Rainfall Events

```powershell
python import_spatial_to_mongodb.py
```

Creates collections, upserts catchments, seeds rainfall events, runs sample risk assessment, prints report.

### C. Real-time Weather Ingestion + Risk Assessment

```powershell
python integrated_flood_system.py
```

Follow interactive prompts; can opt into continuous monitoring mode.

### D. Weather API Standalone Demo

```powershell
python weather_api_client.py
```

---

## 8. Continuous Monitoring Mode

- Periodically fetches weather API
- Creates rainfall event if data present
- Runs prioritized risk simulations (capacity + area weighted)
- Generates alert dashboard with emoji severity markers

---

## 9. Catchment Linking (Foreign Key Join)

The previous heuristic spatial matching stage (overlap → nearest → estimated) has been refactored.
Pipe features now carry a stable foreign key `ufi` that directly references the primary key of their
parent catchment polygon. The pipeline now:

1. Aggregates pipe stats per `ufi`
2. Loads catchment polygons keyed by `ufi`
3. Performs a dictionary join to build unified records

Runoff coefficient `C` is still heuristically adjusted from land‑use fields (`type`, `management`).
If a catchment has no corresponding pipe data it is currently omitted (optional future flag could
emit zero‑capacity placeholders).

Migration differences vs legacy heuristic output:

| Removed Fields      | Reason                                                                                |
| ------------------- | ------------------------------------------------------------------------------------- |
| `match_type`        | No spatial heuristic performed                                                        |
| `match_score`       | Overlap / distance score obsolete                                                     |
| `match_distance_km` | Nearest neighbour step removed                                                        |
| `area_estimated`    | Area now taken directly from catchment (still estimated only if source value missing) |

New / clarified fields:

- `ufi`: Explicit ID used for joining
- `catchment_id`: Mirrors `ufi` (legacy compatibility)

Benefits: deterministic, faster, simpler to test, and avoids ambiguous matches in dense networks.

---

## 10. Extensibility Ideas

- Replace heuristic spatial matcher with full polygon intersection + area weighting
- Introduce temporal resolution finer than 1h / 30min with hyetograph normalization
- Enable ensemble forecast ingestion for probabilistic risk bands
- Add GeoJSON 2dsphere index & store full geometry objects
- Support machine learning calibration of C and Qcap from historical events
- Provide REST API / FastAPI service layer for external clients

---

## 11. Issue Reporting (Crowdsourced Field Input)

An integrated issue reporting collection allows field / citizen users to submit flood related problems (e.g. flooded road, blocked drain) with geolocation, photos, and optional notes. The lifecycle/status workflow was intentionally simplified (no status or priority fields) to keep ingestion lightweight; enrichment or triage can be layered externally later if needed.

Schema (simplified current form):

```json
{
  "issue_id": "ISSUE_ab12cd34ef",
  "issue_type": "Flooded road",
  "description": "Water over curb near Oak Ave.",
  "location": { "type": "Point", "coordinates": [115.8614, -31.95224] },
  "user": {
    "uid": "firebase123",
    "display_name": "Jane",
    "email": "jane@example.com"
  },
  "photo_urls": ["https://.../img1.jpg"],
  "created_at": "2025-09-27T08:12:00Z"
}
```

---

## 12. FastAPI Service & New Point Risk Endpoint

The project now includes a FastAPI application (see `main.py`) exposing simulation and risk services.

Base URL (default dev run): `http://localhost:8000/api/v1`

### Existing Endpoint

POST `/simulate`
Runs a bespoke simulation for arbitrary rainfall time series and parameters. (See automatic docs at `/docs` for schema.)

### New Endpoint: Point-Based Catchment Risk

POST `/risk/point`

Purpose: Given a geographic coordinate (lon/lat), identify the catchment whose stored bounding box contains the point, run a simulation with a specified (or default) rainfall event, and return its risk metrics.

Request Body:

```json
{
  "lon": 115.857,
  "lat": -31.9553,
  "rainfall_event_id": "design_10yr"
}
```

If `rainfall_event_id` is omitted the service falls back to `design_10yr`, or the first available rainfall event if that one does not exist.

Successful Response Example:

```json
{
  "catchment_id": "WcmWill",
  "catchment_name": "WcmWill",
  "rainfall_event_id": "design_10yr",
  "max_risk": 0.742,
  "risk_level": "high",
  "parameters": { "C": 0.6, "A_km2": 12.92, "Qcap_m3s": 73.323 },
  "max_risk_time": "2025-09-25T03:00:00Z",
  "max_risk_point": {
    "t": "2025-09-25T03:00:00Z",
    "i": 30.0,
    "Qrunoff": 64.6,
    "L": 0.881,
    "R": 0.742
  }
}
```

Error (no catchment match):

```json
{
  "detail": "No catchment found for provided point"
}
```

### How It Works Internally

1. Loads all catchments (Mongo) and filters those whose stored bounding box (`location.bounds`) contains the point.
2. Chooses the smallest-area candidate if multiple.
3. Retrieves the rainfall event.
4. Runs `simulate_catchment` using the catchment's hydraulic parameters.
5. Computes a categorical risk level from the continuous `max_risk`.

### Running the API

```powershell
uvicorn main:app --reload --port 8000
```

Visit interactive docs at: `http://localhost:8000/docs`

### Notes & Future Enhancements

- Bounding box containment is a proxy; replace with real polygon point-in-polygon once geometries are stored.
- Consider caching catchments in-memory to avoid per-request full scans (trivial for current dataset size).
- Add optional parameter to return full series or summary only (currently only peak info returned; full internal series is accessible via code changes if needed).

Key points:

- `location` is GeoJSON Point → enables geospatial `$near` queries.
- `issue_id` is a generated business key (distinct from Mongo `_id`).
- Optional free‑form `notes` can be appended / replaced.

CLI Commands (current set):

```powershell
# Create a report
python -m urban_flooding.cli issue-create --type "Flooded road" --description "Water over curb" --lat -31.95 --lon 115.86 --uid user123 --notes "Observed after storm cell"

# List recent reports
python -m urban_flooding.cli issue-list --limit 10

# Filter by type or user
python -m urban_flooding.cli issue-list --type "Flooded road"
python -m urban_flooding.cli issue-list --uid user123

# Proximity search (meters)
python -m urban_flooding.cli issue-near --lat -31.95 --lon 115.86 --radius 2000

# Aggregate statistics (count + by_type breakdown)
python -m urban_flooding.cli issue-stats
```

Limitations / future enhancements:

- Reintroduce lifecycle (e.g. open / triaged / resolved) if operational workflow emerges.
- Add controlled vocab or enumeration for `issue_type` (currently free-form validated in downstream logic only).
- Support media attachment metadata (size, mime, checksum) and archival policies.
- Optional linkage to nearest catchment for contextual analytics.

Geospatial queries use a 2dsphere index on the GeoJSON `location` field.

---

## 12. Minimal Programmatic Example (New Imports)

```python
from urban_flooding.persistence.database import FloodingDatabase
from urban_flooding.domain.simulation import simulate_catchment

db = FloodingDatabase()
catchment = db.list_catchments()[0]
rain = db.list_rainfall_events()[0]
result = simulate_catchment(
   rain['rain_mmhr'],
   rain['timestamps_utc'],
   catchment['C'],
   catchment['A_km2'],
   catchment['Qcap_m3s']
)
print(result['max_risk'])
```

---

## 13. Testing / Validation

Pytest unit tests cover hydrology & simulation edge cases:

```powershell
pytest -q
```

Included tests:

- Rational Method discharge formula correctness
- Logistic risk midpoint at L=1 → R=0.5
- Risk increases with higher loading
- Simulation produces series & max_risk
- Zero capacity → extreme (≈1) risk

Additional future test targets:

- Foreign key join integrity (ufi coverage)
- DB persistence round-trip
- Real-time ingestion parsing robustness

---

## 14. Troubleshooting

| Issue                   | Likely Cause                              | Fix                                                 |
| ----------------------- | ----------------------------------------- | --------------------------------------------------- |
| Mongo validation errors | Field type mismatch                       | Coerce types in import script (already implemented) |
| No catchments imported  | Missing `catchments_spatial_matched.json` | Run spatial converter first                         |
| Weather fetch fails     | Network / auth / API down                 | Retry later or mock rainfall event                  |
| Continuous monitor idle | Zero rainfall intensities                 | Use design event via `import_spatial_to_mongodb.py` |

---

## 15. Disclaimer

This code is illustrative and not a replacement for detailed hydrodynamic modeling or regulatory flood studies.

---

## 16. License

Specify license here (e.g., MIT) – currently unspecified.
