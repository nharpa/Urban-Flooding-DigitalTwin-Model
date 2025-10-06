"""Schema helpers migrated from legacy `schemas_v3.py`."""

CATCHMENT_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["catchment_id", "name", "C", "A_km2", "Qcap_m3s"],
        "properties": {
            "_id": {"bsonType": "objectId"},
            "catchment_id": {"bsonType": "string"},
            "name": {"bsonType": "string"},
            "C": {"bsonType": "double", "minimum": 0.0, "maximum": 1.0},
            "A_km2": {"bsonType": "double", "minimum": 0.0},
            "Qcap_m3s": {"bsonType": "double", "minimum": 0.0},
            # Optional centroid (latitude, longitude)
            "centroid": {
                "bsonType": ["array", "null"],
                "items": [
                    {"bsonType": "double"},  # latitude
                    {"bsonType": "double"}   # longitude
                ],
                "minItems": 2,
                "maxItems": 2
            },
            # Optional preserved geometry (GeoJSON Polygon / MultiPolygon)
            "geometry": {
                "bsonType": ["object", "null"],
                "properties": {
                    "type": {"enum": ["Polygon", "MultiPolygon"]},
                    "coordinates": {"bsonType": "array"}
                }
            },
        }
    }
}

SIMULATION_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["simulation_id", "catchment_id", "rain_mmhr", "timestamps_utc", "C", "A_km2", "Qcap_m3s", "series", "max_risk"],
        "properties": {"simulation_id": {"bsonType": "string"}}
    }
}

RAINFALL_EVENT_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["event_id", "name", "rain_mmhr", "timestamps_utc"],
        "properties": {"event_id": {"bsonType": "string"}}
    }
}

# New: Issue reporting schema (GeoJSON point for location, business key issue_id)
ISSUE_REPORT_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "issue_id",
            "issue_type",
            "description",
            "location",
            "user",
            "created_at"
        ],
        "properties": {
            "_id": {"bsonType": "objectId"},
            "issue_id": {"bsonType": "string"},
            "issue_type": {"bsonType": "string"},
            "description": {"bsonType": "string"},
            "location": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {
                    "type": {"enum": ["Point"]},
                    "coordinates": {
                        "bsonType": "array",
                        "items": [{"bsonType": "double"}, {"bsonType": "double"}],
                        "minItems": 2,
                        "maxItems": 2
                    }
                }
            },
            "user": {
                "bsonType": "object",
                "required": ["uid"],
                "properties": {
                    "uid": {"bsonType": "string"},
                    "display_name": {"bsonType": ["string", "null"]},
                    "email": {"bsonType": ["string", "null"]}
                }
            },
            "created_at": {"bsonType": "date"},
        }
    }
}


def create_collections_with_validation(db):
    existing = db.list_collection_names()
    if "catchments" not in existing:
        db.create_collection("catchments", validator=CATCHMENT_SCHEMA)
    else:
        db.command("collMod", "catchments", validator=CATCHMENT_SCHEMA)
    if "simulations" not in existing:
        db.create_collection("simulations", validator=SIMULATION_SCHEMA)
    else:
        db.command("collMod", "simulations", validator=SIMULATION_SCHEMA)
    if "rainfall_events" not in existing:
        db.create_collection(
            "rainfall_events", validator=RAINFALL_EVENT_SCHEMA)
    else:
        db.command("collMod", "rainfall_events",
                   validator=RAINFALL_EVENT_SCHEMA)
    if "issue_reports" not in existing:
        db.create_collection("issue_reports", validator=ISSUE_REPORT_SCHEMA)
    else:
        db.command("collMod", "issue_reports", validator=ISSUE_REPORT_SCHEMA)


def create_geospatial_indexes(db):
    """Create geospatial indexes.

    Legacy bounding-box scalar indexes removed. If geometry is present as
    GeoJSON Polygon/MultiPolygon, create a 2dsphere index to enable spatial
    queries (e.g. future point-in-polygon pipelines).
    """
    try:
        db.catchments.create_index([("geometry", "2dsphere")])
    except Exception as e:  # pragma: no cover
        print(f"Warning: could not create 2dsphere index on geometry: {e}")
