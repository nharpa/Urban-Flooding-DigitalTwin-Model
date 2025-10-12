# Urban Flooding Digital Twin

A comprehensive digital twin system for urban flooding risk assessment that combines real-time monitoring, spatial analysis, and predictive modeling. This system integrates drainage infrastructure data, weather observations, and hydraulic modeling to provide actionable flood risk insights.

## Overview

The Urban Flooding Digital Twin provides:

- **Real-time Monitoring**: Continuous assessment of flood risk using live weather data
- **Spatial Intelligence**: Point-in-polygon risk assessment for any geographic location
- **Hydraulic Modeling**: Rational Method-based runoff calculations with capacity loading analysis
- **Risk Categorization**: Intelligent risk scoring with categorical levels (Very Low to Very High)
- **API Integration**: RESTful endpoints for external system integration
- **Issue Reporting**: Community-driven flood incident reporting system

> **Note**: This is a research and prototyping platform designed for rapid iteration and clear data flow, not a production-grade flood forecasting system.

## Architecture

### Core Components

| Component               | Description                                                |
| ----------------------- | ---------------------------------------------------------- |
| **FastAPI Service**     | REST API with authentication and real-time monitoring      |
| **MongoDB Database**    | Persistent storage for catchments, events, and simulations |
| **Spatial Engine**      | GeoJSON processing and point-in-polygon operations         |
| **Risk Algorithm**      | Hydraulic modeling with sigmoid risk transformation        |
| **Weather Integration** | External API client for real-time weather data             |
| **Background Monitor**  | Continuous risk assessment across all catchments           |

### Key Concepts

| Concept            | Description                                                                |
| ------------------ | -------------------------------------------------------------------------- |
| **Catchment**      | Spatial drainage area with hydraulic properties (`A_km2`, `C`, `Qcap_m3s`) |
| **Rainfall Event** | Time series of rainfall intensities with metadata                          |
| **Simulation**     | Runoff calculation and risk assessment for a catchment-event pair          |
| **Risk Score**     | Sigmoid-transformed loading ratio: `R = 1/(1 + exp(-k(L-1)))`              |

---

## Repository Structure

```
urban_flooding_digitaltwin/
├── main.py                          # FastAPI application entry point
├── docker-compose.yml               # MongoDB containerization
├── requirements.txt                 # Python dependencies
├── init_db.py                      # Database initialization script
├── batch_simulation.py             # Batch risk assessment across catchments
├── spatial_import.py               # Spatial data processing pipeline
├── data/                           # Input data files
│   ├── catchments_spatial_matched.json
│   ├── PerthMetroCatchments.geojson
│   ├── PerthMetroStormDrainPipe.geojson
│   ├── PipeMaterials.json
│   └── RainfallEvents.json
├── digital_twin/                   # Core application modules
│   ├── auth/                      # Authentication & configuration
│   │   ├── auth.py               # Bearer token authentication
│   │   └── config.py             # Environment settings management
│   ├── database/                  # Data persistence layer
│   │   ├── database_utils.py     # MongoDB operations
│   │   └── database_schema.py    # Collection schemas & validation
│   ├── services/                  # Business logic services
│   │   ├── risk_algorithm.py     # Hydraulic modeling & risk calculation
│   │   ├── realtime_monitor.py   # Background monitoring service
│   │   └── realtime_weather_service.py  # Weather API integration
│   └── spatial/                   # Spatial data processing
│       ├── spatial_utils.py      # Geometric utilities
│       └── spatial_data_processing.py  # GeoJSON processing pipeline
└── api/                           # REST API implementation
    └── v1/
        ├── routes.py             # API router configuration
        └── endpoints/            # API endpoint implementations
            ├── simulate.py       # Catchment simulation endpoint
            ├── risk.py          # Point-based risk assessment
            └── report.py        # Issue reporting endpoint
```

---

## Data Flow Pipeline

### 1. Spatial Data Processing

```
GeoJSON Files → spatial_data_processing.py → catchments_spatial_matched.json → MongoDB
```

- **Input**: Perth catchment polygons and storm drain pipe networks (GeoJSON)
- **Processing**: Pipe aggregation by subcatchment, hydraulic capacity calculations
- **Output**: Spatially-matched catchments with hydraulic properties

### 2. Database Initialization

```
python init_db.py → MongoDB Collections + Indexes + Validation
```

- Creates collections: `catchments`, `rainfall_events`, `simulations`, `issue_reports`
- Establishes indexes for performance and spatial queries
- Applies JSON schema validation

### 3. Risk Assessment Workflow

```
Location (lat/lon) → find_catchment_for_point() → simulate_catchment() → Risk Score
```

- **Point Query**: Find containing catchment using polygon geometry
- **Simulation**: Apply Rational Method with rainfall time series
- **Risk Calculation**: Transform loading ratio to risk score (0-1)

### 4. Real-time Monitoring

```
Weather API → rainfall_events → Background Simulations → Alerts
```

- Periodic weather data ingestion from external APIs
- Automated risk assessment across all catchments
- Alert generation for high-risk conditions (R ≥ 0.6)

---

## Database Schema

### Collections

| Collection        | Purpose                                                          | Key Fields                                                   |
| ----------------- | ---------------------------------------------------------------- | ------------------------------------------------------------ |
| `catchments`      | Drainage catchments with spatial and hydraulic properties        | `catchment_id`, `name`, `A_km2`, `C`, `Qcap_m3s`, `geometry` |
| `rainfall_events` | Time series rainfall data (design storms, historical, real-time) | `event_id`, `name`, `rain_mmhr[]`, `timestamps_utc[]`        |
| `simulations`     | Risk assessment results                                          | `simulation_id`, `catchment_id`, `max_risk`, `series[]`      |
| `issue_reports`   | Community-reported flooding issues                               | `issue_id`, `location`, `issue_type`, `description`          |

### Catchment Document Structure

```json
{
  "catchment_id": "perth_cbd_c1",
  "name": "Perth CBD Catchment 1",
  "A_km2": 1.45,
  "C": 0.85,
  "Qcap_m3s": 3.2,
  "geometry": {
    "type": "Polygon",
    "coordinates": [[...]]
  },
  "pipe_count": 12,
  "total_length_m": 2840,
  "avg_diameter_mm": 450,
  "created_at": "2025-10-12T10:30:00Z"
}
```

### Rainfall Event Document Structure

```json
{
  "event_id": "design_10yr",
  "name": "10-Year Design Storm",
  "event_type": "design",
  "rain_mmhr": [5.2, 12.8, 28.5, 50.1, 35.6, 10.2],
  "timestamps_utc": ["2025-10-12T00:00:00Z", "2025-10-12T01:00:00Z", ...],
  "total_rainfall_mm": 142.4,
  "peak_intensity_mmhr": 50.1,
  "duration_hours": 6
}
```

---

## Risk & Hydraulic Model

### Runoff Calculation (Rational Method)

```
Q = 0.278 × C × i × A
```

Where:

- **Q** = Runoff discharge (m³/s)
- **C** = Runoff coefficient (dimensionless, 0-1)
- **i** = Rainfall intensity (mm/hr)
- **A** = Catchment area (km²)

### Capacity Loading Analysis

```
L = Q / Qcap_m3s
```

- **L** = Loading ratio (dimensionless)
- **Qcap_m3s** = Drainage system capacity (m³/s)

### Risk Score Transformation

```
R = 1 / (1 + exp(-k × (L - 1)))
```

- **R** = Risk score (0-1)
- **k** = Steepness parameter (~8)
- **L** = Loading ratio

### Risk Categories

| Risk Score    | Category  | Color     | Action              |
| ------------- | --------- | --------- | ------------------- |
| R < 0.2       | Very Low  | 🟢 Green  | Normal operations   |
| 0.2 ≤ R < 0.4 | Low       | 🟡 Yellow | Monitor conditions  |
| 0.4 ≤ R < 0.6 | Medium    | 🟠 Orange | Increased vigilance |
| 0.6 ≤ R < 0.8 | High      | 🔴 Red    | Alert conditions    |
| R ≥ 0.8       | Very High | 🟣 Purple | Emergency response  |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Docker & Docker Compose** (for MongoDB)
- **Git** (for repository access)

### 1. Clone & Setup Environment

```powershell
git clone <repository-url>
cd Urban-Flooding-DigitalTwin-Model/urban_flooding_digitaltwin

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file and configure settings:

```powershell
copy .env.example .env
```

Edit `.env` with your configuration:

```env
# Database Configuration
MONGODB_NAME=urban_flooding_db
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=your_secure_password

# API Configuration
API_TOKEN=your_api_token_here

# Weather API (optional)
WEATHER_API_URL=https://api.weather.com/v1
WEATHER_API_TOKEN=your_weather_token
```

### 3. Start Database

```powershell
# Start MongoDB in background
docker-compose up -d

# Verify container health
docker-compose ps
```

### 4. Initialize Database

```powershell
# Create collections, indexes, and validation rules
python init_db.py
```

### 5. Process Spatial Data

```powershell
# Process GeoJSON files and populate catchments
python spatial_import.py
```

### 6. Start API Service

```powershell
# Start FastAPI server
python main.py

# Or with custom port
python main.py --port 8080
```

## The API will be available at `http://localhost:8008` with interactive documentation at `http://localhost:8008/docs`.

## 🔌 API Endpoints

The FastAPI service provides RESTful endpoints for integration with external systems.

### Authentication

All endpoints require Bearer token authentication:

```http
Authorization: Bearer your_api_token_here
```

### Core Endpoints

#### 1. Point Risk Assessment

**POST** `/api/v1/risk/point`

Assess flood risk for a specific geographic location.

```json
{
  "lon": 115.8605,
  "lat": -31.9505,
  "rainfall_event_id": "design_10yr"
}
```

**Response:**

```json
{
  "catchment_id": "perth_cbd_c1",
  "catchment_name": "Perth CBD Catchment 1",
  "rainfall_event_id": "design_10yr",
  "max_risk": 0.742,
  "risk_level": "High",
  "catchment_area_km2": 1.45,
  "runoff_coefficient": 0.85,
  "pipe_capacity_m3s": 3.2,
  "max_risk_time": "2025-10-12T02:00:00Z"
}
```

#### 2. Catchment Simulation

**POST** `/api/v1/simulate`

Run hydraulic simulation for specific catchment parameters.

```json
{
  "catchment_id": "test_catchment",
  "rain_mm_per_hr": [5.2, 12.8, 28.5, 50.1, 35.6, 10.2],
  "timestamps_utc": ["2025-10-12T00:00:00Z", "2025-10-12T01:00:00Z", ...],
  "C": 0.85,
  "A_km2": 1.45,
  "Qcap_m3s": 3.2
}
```

#### 3. Issue Reporting

**POST** `/api/v1/report`

Submit community flood reports.

```json
{
  "issue_type": "Flooded road",
  "description": "Water over road surface, difficult to pass",
  "location": {
    "latitude": -31.9505,
    "longitude": 115.8605
  },
  "user": {
    "uid": "user123",
    "display_name": "John Doe",
    "email": "john@example.com"
  }
}
```

### Interactive Documentation

Visit `http://localhost:8008/docs` for complete API documentation with interactive testing interface.

---

## 📊 Usage Examples

### Python API Usage

```python
from digital_twin.database.database_utils import FloodingDatabase
from digital_twin.services.risk_algorithm import simulate_catchment
from digital_twin.spatial.spatial_utils import find_catchment_for_point

# Initialize database connection
db = FloodingDatabase()

# Find catchment for a specific point
catchments = db.list_catchments()
catchment = find_catchment_for_point(catchments, lon=115.8605, lat=-31.9505)

if catchment:
    # Get rainfall event
    rainfall_event = db.get_rainfall_event("design_10yr")

    # Run simulation
    result = simulate_catchment(
        rain_mmhr=rainfall_event["rain_mmhr"],
        timestamps_utc=rainfall_event["timestamps_utc"],
        C=catchment["C"],
        A_km2=catchment["A_km2"],
        Qcap_m3s=catchment["Qcap_m3s"]
    )

    print(f"Maximum risk: {result['max_risk']:.3f}")

# Clean up
db.close()
```

### Batch Risk Assessment

```powershell
# Run batch simulation across all catchments
python batch_simulation.py
```

This generates a comprehensive risk assessment report saved to `simulation_outputs/` with:

- Risk scores for each catchment
- Time series analysis
- Peak risk identification
- Categorical risk assignments

### Real-time Monitoring

The system includes automatic background monitoring when the API service is running. To disable:

```powershell
$env:DISABLE_MONITORING = "true"
python main.py
```

---

## Configuration

### Environment Variables

| Variable                     | Description                         | Required | Default             |
| ---------------------------- | ----------------------------------- | -------- | ------------------- |
| `MONGODB_NAME`               | Database name                       | Yes      | `urban_flooding_db` |
| `MONGO_INITDB_ROOT_USERNAME` | MongoDB username                    | Yes      | -                   |
| `MONGO_INITDB_ROOT_PASSWORD` | MongoDB password                    | Yes      | -                   |
| `MONGODB_URL`                | MongoDB connection URL              | No       | `localhost:27017`   |
| `API_TOKEN`                  | Bearer token for API authentication | Yes      | -                   |
| `WEATHER_API_URL`            | External weather service URL        | No       | -                   |
| `WEATHER_API_TOKEN`          | Weather service API key             | No       | -                   |
| `DISABLE_MONITORING`         | Disable background monitoring       | No       | `false`             |

### Data Files

| File                               | Description                      | Source                           |
| ---------------------------------- | -------------------------------- | -------------------------------- |
| `PerthMetroCatchments.geojson`     | Catchment polygon geometries     | Perth Metropolitan Government    |
| `PerthMetroStormDrainPipe.geojson` | Storm drain pipe network         | Perth Water Corporation          |
| `PipeMaterials.json`               | Manning coefficients by material | Engineering standards            |
| `RainfallEvents.json`              | Design storm definitions         | Australian Bureau of Meteorology |

---

## Development

### Running Tests

```powershell
# Install test dependencies
pip install pytest httpx

# Run test suite
pytest tests/
```

### Code Quality

```powershell
# Format code
black digital_twin/ api/

# Type checking
mypy digital_twin/

# Linting
flake8 digital_twin/ api/
```

### Docker Development

```powershell
# Build development container
docker build -t urban-flooding-dt .

# Run with mounted code
docker run -v ${PWD}:/app -p 8008:8008 urban-flooding-dt
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add docstrings to all public functions and classes
- Include unit tests for new functionality
- Update README for significant changes

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Western Australian Department of Water and Environmental Regulation
- Australian Bureau of Meteorology for rainfall statistics

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
