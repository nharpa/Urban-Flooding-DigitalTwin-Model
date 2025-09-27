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


def create_geospatial_indexes(db):
    db.catchments.create_index([
        ("location.bounds.min_lon", 1),
        ("location.bounds.min_lat", 1),
        ("location.bounds.max_lon", 1),
        ("location.bounds.max_lat", 1),
    ])
