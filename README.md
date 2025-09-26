# Urban Flooding Digital Twin (Spatial + Real-time Prototype)

This repository contains a prototype "digital twin" style workflow for urban flooding risk assessment. It integrates:

- Spatial processing of drainage pipe network GeoJSON and hydrographic catchment polygons
- Automated spatial (overlap / nearest / heuristic) matching to derive catchment hydraulic attributes
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
   - Aggregates pipe segments per subcatchment → capacity, length, diameter stats
   - Extracts polygon bounds / centroid / area (or estimates if missing)
   - Performs spatial heuristic matching (overlap > nearest > estimated)
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

## 9. Spatial Matching Logic (Heuristic)

Priority order:

1. Bounding box overlap score (overlap ratio × distance decay)
2. Nearest centroid within 0.1° (~11 km) with distance → score + confidence
3. Fallback area estimation from pipe network extent & density

Adjusts runoff coefficient `C` by interpreted land-use hints (urban/residential/rural).

---

## 10. Extensibility Ideas

- Replace heuristic spatial matcher with full polygon intersection + area weighting
- Introduce temporal resolution finer than 1h / 30min with hyetograph normalization
- Enable ensemble forecast ingestion for probabilistic risk bands
- Add GeoJSON 2dsphere index & store full geometry objects
- Support machine learning calibration of C and Qcap from historical events
- Provide REST API / FastAPI service layer for external clients

---

## 11. Minimal Programmatic Example (New Imports)

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

## 12. Testing / Validation

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

- Spatial matching heuristics correctness
- DB persistence round-trip
- Real-time ingestion parsing robustness

---

## 13. Troubleshooting

| Issue                   | Likely Cause                              | Fix                                                 |
| ----------------------- | ----------------------------------------- | --------------------------------------------------- |
| Mongo validation errors | Field type mismatch                       | Coerce types in import script (already implemented) |
| No catchments imported  | Missing `catchments_spatial_matched.json` | Run spatial converter first                         |
| Weather fetch fails     | Network / auth / API down                 | Retry later or mock rainfall event                  |
| Continuous monitor idle | Zero rainfall intensities                 | Use design event via `import_spatial_to_mongodb.py` |

---

## 14. Disclaimer

This code is illustrative and not a replacement for detailed hydrodynamic modeling or regulatory flood studies.

---

## 15. License

Specify license here (e.g., MIT) – currently unspecified.
