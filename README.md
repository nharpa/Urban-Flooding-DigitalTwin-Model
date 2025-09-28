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

## 3. Data Flow Overview (Geometry‑First)

1. Input GeoJSON files (pipes + catchment polygons) are processed by `urban_flooding.spatial.geojson_converter` (run via `python -m urban_flooding.spatial.geojson_converter` or its `main()`):

- Aggregates pipe segments per subcatchment (key = `ufi`) → hydraulic metrics (`Qcap_m3s`, `pipe_count`, `total_length_m`, diameter stats). No centroids / bounds are derived here anymore.
- Loads catchment polygons preserving full GeoJSON `geometry` and core attributes (area, type, management, names).
- Performs a direct dictionary join on `ufi` to associate hydraulic summaries with polygon geometry.
- Writes `data/catchments_spatial_matched.json` containing: `catchment_id`, `ufi`, `name`, `A_km2`, hydraulic stats, heuristic runoff coefficient `C`, and full `geometry`.

2. The CLI command `python -m urban_flooding.cli ingest-spatial --file data/catchments_spatial_matched.json --design-events` loads the JSON and upserts catchments into MongoDB (schema now supports a GeoJSON-like `geometry` field). Legacy helper scripts remain but are deprecated.
3. Design rainfall events are created (2, 10, 50, 100 year + historical template) via `python -m urban_flooding.cli design-events`.
4. Simulations use `domain.simulation.simulate_catchment` to generate time series and risk metrics.
5. Real‑time weather API ingestion (`ingestion.weather_client`) converts observations to rainfall events.
6. Higher-level orchestration (dashboards, monitoring loop) is provided by `services.integrated_system` and CLI commands (`risk-assess`, `monitor`).

Key Change vs Legacy: Bounding box / centroid heuristics were removed; spatial accuracy now derives from authentic polygon geometries enabling precise point‑in‑polygon operations (already used in the point risk endpoint with a temporary fallback for legacy documents lacking geometry).

---

## 4. MongoDB Schema Highlights (Updated)

Collections:

- `catchments`: Hydraulic + spatial attributes with preserved polygon `geometry` (GeoJSON object), pipe stats, heuristic runoff coefficient. Legacy documents may still contain `location.bounds` without full geometry (migration guidance below).
- `rainfall_events`: Time series rainfall definitions.
- `simulations`: Simulation outputs (series + max_risk + references).
- `issues`: Optional crowdsourced field issue reports (point locations) – see Issue Reporting section.

Indexes (see `urban_flooding/persistence/schemas.py`):

- Functional: `catchment_id` (unique), `simulation_id`, `event_id`.
- Query support: compound indexes for rainfall event lookups and simulation retrieval.
- Spatial: Attempted `2dsphere` index on `geometry` (if present) prepared for future geospatial queries; legacy bounding box compound index removed.

Geometry Field:

```jsonc
{
  "geometry": { "type": "Polygon" | "MultiPolygon", "coordinates": [...] }
}
```

Validation intentionally keeps the geometry schema permissive (basic shape/type) to allow upstream ingestion of varied polygon complexities. Downstream spatial operations (e.g., point‑in‑polygon) assume valid winding/order; a future enhancement may add optional geometry validation / repair.

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
- MongoDB (run via provided `docker-compose.yml` or an existing deployment)

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

## 7. Database Deployment & Initialization (New)

The quickest way to bring up MongoDB with the correct database name and persistent volumes is via Docker Compose (ships with this repo).

Start MongoDB (foreground):

```powershell
docker compose up
```

Or run detached:

```powershell
docker compose up -d
```

Health check waits for the server to respond before marking the container healthy.

Once the container is running, initialize (or re‑initialize) the collections, schema validators, and indexes. This is idempotent and safe to repeat after code updates.

Using the CLI command:

```powershell
python -m urban_flooding.cli init-db
```

Or using the standalone helper script (handy inside other automation):

```powershell
python scripts/init_db.py
```

If you are using a remote / authenticated Mongo instance set `MONGODB_URI` before running the init command. Example:

```powershell
$env:MONGODB_URI = "mongodb://user:pass@remote-host:27017/?authSource=admin"
python -m urban_flooding.cli init-db
```

You should see a list of initialized collection names. At this point the database layer is ready for spatial ingestion and rainfall event seeding.

> Next Planned Enhancement: After the pending `geojson_converter` fix, the `init-db` command will be extended (or an additional `bootstrap` command added) to automatically process GeoJSON inputs and populate the `catchments` collection in one step.

---

## 8. Typical Workflow (CLI First)

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

Legacy scripts (`import_spatial_to_mongodb.py`, `integrated_flood_system.py`, `geojson_converter_spatial.py`) remain as thin wrappers for backward compatibility but are deprecated. Preferred modern equivalents:

| Legacy Script                  | Replacement CLI Command                                                                                   |
| ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| `geojson_converter_spatial.py` | `python -m urban_flooding.spatial.geojson_converter` (or run via conversion invoked in workflow)          |
| `import_spatial_to_mongodb.py` | `python -m urban_flooding.cli ingest-spatial --file data/catchments_spatial_matched.json --design-events` |
| `integrated_flood_system.py`   | `python -m urban_flooding.cli risk-assess` / `monitor` / `realtime-fetch` combinations                    |

Use the CLI variants for consistent logging, argument validation, and future feature support.

### D. Weather API Standalone Demo

```powershell
python weather_api_client.py
```

---

## 9. Continuous Monitoring Mode

- Periodically fetches weather API
- Creates rainfall event if data present
- Runs prioritized risk simulations (capacity + area weighted)
- Generates alert dashboard with emoji severity markers

---

## 10. Catchment Linking (Deterministic Geometry Join)

Heuristic spatial matching (overlap → nearest → estimated) has been fully retired. Each pipe feature
includes a stable foreign key `ufi` pointing to its parent catchment polygon. During conversion:

1. Pipe hydraulics are aggregated per `ufi` (capacity, pipe counts, diameter stats).
2. Catchment polygons are loaded with preserved GeoJSON `geometry` keyed by `ufi`.
3. A direct dictionary join produces unified catchment records embedding hydraulic metrics and geometry.

Runoff coefficient `C` is heuristically derived from land‑use / management attributes. Catchments lacking
pipe data are currently omitted (future option: output zero‑capacity records for completeness).

Preserved Fields:

- `ufi` / `catchment_id`: Stable identifier (mirrored for backward compatibility).
- `geometry`: Full Polygon / MultiPolygon for precise spatial queries (e.g., point‑in‑polygon risk lookups).

Removed Legacy Artifacts: `match_type`, `match_score`, `match_distance_km`, `area_estimated`, and derived
`location.bounds` / `location.center` fields—these are no longer needed because authoritative geometry is stored.

Benefits: Deterministic joins, improved spatial fidelity, reduced complexity, and consistent reproducibility across reruns.

---

## 11. Extensibility Ideas (Forward Look)

- Area‑weighted rainfall / runoff distribution for partially intersecting polygons (if sub‑catchment nesting introduced).
- Geometry QA & repair pipeline (self‑intersection fixing, winding order normalization) pre‑ingestion.
- Pipe geometry capture (LineString → aggregated MultiLineString per catchment) for map visualization & hydraulic distribution modeling.
- Temporal resolution refinement (sub‑hour hyetographs) with intensity normalization & convolution against catchment response curves.
- Ensemble / probabilistic rainfall event ingestion (e.g., blending forecasts) to derive risk bands (P10 / P50 / P90).
- Machine learning calibration of runoff coefficient `C` and effective capacity scaling using historical event + observation pairs.
- Incremental geospatial caching layer with spatial index acceleration (R‑tree / Mongo 2dsphere queries) for high request volumes.
- Streaming ingestion mode (websocket or pub/sub) for near real‑time rainfall updates driving rolling risk nowcasts.

---

## 12. Migration Notes (Legacy Spatial Records)

Some earlier datasets persisted catchments with only `location.bounds` / `location.center` and without full `geometry`.
The new geometry‑first logic introduces polygon point‑in‑polygon selection and will fall back to bounds only when
`geometry` is missing. To fully migrate:

1. Re‑run the spatial conversion pipeline (`python -m urban_flooding.spatial.geojson_converter`) to produce an updated `catchments_spatial_matched.json` containing `geometry`.
2. Use the CLI to ingest: `python -m urban_flooding.cli ingest-spatial --file data/catchments_spatial_matched.json`.
3. (Optional cleanup) Remove legacy fields from existing records lacking geometry:

```python
from urban_flooding.persistence.database import FloodingDatabase
db = FloodingDatabase()
updated = 0
for c in db.list_catchments():
  if 'geometry' not in c or not c['geometry']:
    # Attempt to look up replacement in refreshed JSON by ufi
    # (Assuming you loaded the file into memory as new_data keyed by ufi)
    pass
```

Recommended Approach: Instead of in‑place patching, drop & re‑ingest the `catchments` collection if no downstream
references rely on stable `_id` values. The catchment `catchment_id` / `ufi` keys remain stable across regenerations.

Deprecation Timeline: The fallback to bounding boxes in the risk endpoint will be removed in a future release once
all production datasets contain polygon `geometry`.

---

## 13. Issue Reporting (Crowdsourced Field Input)

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

## 14. FastAPI Service & New Point Risk Endpoint

The project now includes a FastAPI application (see `main.py`) exposing simulation and risk services.

Base URL (default dev run): `http://localhost:8000/api/v1`

### Existing Endpoint

POST `/simulate`
Runs a bespoke simulation for arbitrary rainfall time series and parameters. (See automatic docs at `/docs` for schema.)

### New Endpoint: Point-Based Catchment Risk

POST `/risk/point`

Purpose: Given a geographic coordinate (lon/lat), identify the catchment polygon that contains the point (geometry first; falls back to legacy bounding boxes only if geometry absent), run a simulation with a specified (or default) rainfall event, and return risk metrics.

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

1. Loads (or cached) catchments from MongoDB.
2. Attempts polygon point‑in‑polygon test (shapely via geopandas) against preserved `geometry` for each catchment.
3. If no geometries are present (legacy docs), falls back to bounding box containment of `location.bounds`.
4. When multiple polygons contain the point (rare overlaps), selects the smallest area polygon to minimize ambiguity.
5. Retrieves (or defaults) the rainfall event.
6. Runs `simulate_catchment` with hydraulic parameters.
7. Derives categorical risk from the continuous `max_risk` value.

### Running the API

```powershell
uvicorn main:app --reload --port 8000
```

Visit interactive docs at: `http://localhost:8000/docs`

### Notes & Future Enhancements

- Geometry-first already implemented; remove fallback code once all legacy records have geometry.
- Consider in-memory caching with TTL or change stream invalidation for higher throughput deployments.
- Add optional parameter to return full simulation series (currently returns peak summary only).
- Potential: expose nearest-catchment explanation (distance to polygon boundary) for transparency.

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

## 15. Minimal Programmatic Example (New Imports)

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

## 16. Testing / Validation

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

## 17. Troubleshooting

| Issue                   | Likely Cause                              | Fix                                                 |
| ----------------------- | ----------------------------------------- | --------------------------------------------------- |
| Mongo validation errors | Field type mismatch                       | Coerce types in import script (already implemented) |
| No catchments imported  | Missing `catchments_spatial_matched.json` | Run spatial converter first                         |
| Weather fetch fails     | Network / auth / API down                 | Retry later or mock rainfall event                  |
| Continuous monitor idle | Zero rainfall intensities                 | Use design event via `import_spatial_to_mongodb.py` |

---

## 18. Disclaimer

This code is illustrative and not a replacement for detailed hydrodynamic modeling or regulatory flood studies.

---

## 19. License

Specify license here (e.g., MIT) – currently unspecified.
