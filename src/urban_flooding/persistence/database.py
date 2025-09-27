"""Database adapter (MongoDB) for Urban Flooding Digital Twin.

Migrated from legacy `database_v3.py`.
"""
from datetime import datetime
from typing import List, Dict, Optional
import os
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.collection import Collection
from .schemas import create_collections_with_validation, create_geospatial_indexes


class FloodingDatabase:
    """MongoDB database operations class with spatial query support."""

    def __init__(self, connection_uri: str = None, db_name: str = "urban_flooding_dt"):
        self.uri = connection_uri or os.getenv(
            "MONGODB_URI", "mongodb://localhost:27017/")
        self.client = MongoClient(self.uri)
        self.db: Database = self.client[db_name]
        create_collections_with_validation(self.db)
        self.catchments: Collection = self.db["catchments"]
        self.simulations: Collection = self.db["simulations"]
        self.rainfall_events: Collection = self.db["rainfall_events"]
        self._create_indexes()

    def _create_indexes(self):
        self.catchments.create_index("catchment_id", unique=True)
        self.catchments.create_index("name")
        self.catchments.create_index("C")
        self.catchments.create_index("Qcap_m3s")
        self.catchments.create_index("pipe_count")
        try:
            create_geospatial_indexes(self.db)
        except Exception as e:
            print(f"Error creating geospatial indexes: {e}")
        self.simulations.create_index("simulation_id", unique=True)
        self.simulations.create_index(
            [("catchment_id", ASCENDING), ("created_at", DESCENDING)])
        self.simulations.create_index("max_risk")
        self.simulations.create_index("rainfall_event_id")
        self.rainfall_events.create_index("event_id", unique=True)
        self.rainfall_events.create_index("event_type")
        self.rainfall_events.create_index("return_period_years")

    def save_catchment_full(self, catchment_data: Dict) -> str:
        required_fields = ["catchment_id", "name", "C", "A_km2", "Qcap_m3s"]
        for field in required_fields:
            if field not in catchment_data:
                raise ValueError(f"Missing required field: {field}")
        if "created_at" not in catchment_data:
            catchment_data["created_at"] = datetime.utcnow()
        catchment_data["updated_at"] = datetime.utcnow()
        self.catchments.replace_one(
            {"catchment_id": catchment_data["catchment_id"]}, catchment_data, upsert=True)
        return catchment_data["catchment_id"]

    def save_catchment(self, catchment_id: str, name: str, C: float, A_km2: float, Qcap_m3s: float, **kwargs) -> str:
        doc = {"catchment_id": catchment_id, "name": name, "C": C,
               "A_km2": A_km2, "Qcap_m3s": Qcap_m3s, "updated_at": datetime.utcnow()}
        existing = self.catchments.find_one({"catchment_id": catchment_id})
        doc["created_at"] = existing.get(
            "created_at", datetime.utcnow()) if existing else datetime.utcnow()
        for k, v in kwargs.items():
            if v is not None:
                doc[k] = v
        self.catchments.replace_one(
            {"catchment_id": catchment_id}, doc, upsert=True)
        return catchment_id

    def find_catchments_by_location(self, lon: float, lat: float, max_distance_km: float = 10.0) -> List[Dict]:
        degree_offset = max_distance_km / 111.0
        query = {"location.center.lon": {"$gte": lon - degree_offset, "$lte": lon + degree_offset},
                 "location.center.lat": {"$gte": lat - degree_offset, "$lte": lat + degree_offset}}
        return list(self.catchments.find(query, {"_id": 0}))

    def find_catchments_in_bounds(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> List[Dict]:
        query = {"location.center.lon": {"$gte": min_lon, "$lte": max_lon},
                 "location.center.lat": {"$gte": min_lat, "$lte": max_lat}}
        return list(self.catchments.find(query, {"_id": 0}))

    # alias
    def get_catchment_with_pipes(self, catchment_id: str) -> Optional[Dict]:
        return self.catchments.find_one({"catchment_id": catchment_id}, {"_id": 0})

    def get_catchments_by_capacity(self, min_capacity: float = None, max_capacity: float = None) -> List[Dict]:
        query = {}
        if min_capacity is not None:
            query["Qcap_m3s"] = {"$gte": min_capacity}
        if max_capacity is not None:
            if "Qcap_m3s" in query:
                query["Qcap_m3s"]["$lte"] = max_capacity
            else:
                query["Qcap_m3s"] = {"$lte": max_capacity}
        return list(self.catchments.find(query, {"_id": 0}).sort("Qcap_m3s", DESCENDING))

    def save_simulation(self, simulation_id: str, catchment_id: str, rain_mmhr: List[float], timestamps_utc: List[str], C: float, A_km2: float, Qcap_m3s: float, series: List[Dict], max_risk: float, k: float = 8.0, **kwargs) -> str:
        doc = {"simulation_id": simulation_id, "catchment_id": catchment_id, "rain_mmhr": rain_mmhr, "timestamps_utc": timestamps_utc,
               "C": C, "A_km2": A_km2, "Qcap_m3s": Qcap_m3s, "k": k, "series": series, "max_risk": max_risk, "created_at": datetime.utcnow()}
        for k2, v in kwargs.items():
            if v is not None:
                doc[k2] = v
        self.simulations.insert_one(doc)
        return simulation_id

    def get_statistics_with_spatial(self) -> Dict:
        pipeline = [{"$group": {"_id": None, "total_catchments": {"$sum": 1}, "total_area_km2": {"$sum": "$A_km2"}, "avg_capacity_m3s": {"$avg": "$Qcap_m3s"}, "total_pipe_length_km": {"$sum": {"$divide": [
            "$total_pipe_length_m", 1000]}}, "total_pipes": {"$sum": "$pipe_count"}, "with_location": {"$sum": {"$cond": [{"$ne": ["$location", None]}, 1, 0]}}, "estimated_areas": {"$sum": {"$cond": [{"$eq": ["$area_estimated", True]}, 1, 0]}}}}]
        results = list(self.catchments.aggregate(pipeline))
        if results:
            stats = results[0]
            stats.pop("_id")
            return stats
        return {"total_catchments": 0, "total_area_km2": 0, "avg_capacity_m3s": 0, "total_pipe_length_km": 0, "total_pipes": 0, "with_location": 0, "estimated_areas": 0}

    def get_catchment(self, catchment_id: str) -> Optional[Dict]:
        return self.catchments.find_one({"catchment_id": catchment_id}, {"_id": 0})

    def get_simulation(self, simulation_id: str) -> Optional[Dict]:
        return self.simulations.find_one({"simulation_id": simulation_id}, {"_id": 0})

    def get_simulations_by_catchment(self, catchment_id: str, limit: int = 10, skip: int = 0) -> List[Dict]:
        cursor = self.simulations.find({"catchment_id": catchment_id}, {"_id": 0}).sort(
            "created_at", DESCENDING).skip(skip).limit(limit)
        return list(cursor)

    def get_high_risk_simulations(self, risk_threshold: float = 0.7, limit: int = 20) -> List[Dict]:
        cursor = self.simulations.find({"max_risk": {"$gte": risk_threshold}}, {
                                       "_id": 0}).sort("max_risk", DESCENDING).limit(limit)
        return list(cursor)

    def get_simulations_by_date_range(self, days_back: int = 7, limit: int = 100) -> List[Dict]:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        cursor = self.simulations.find({"created_at": {"$gte": cutoff_date}}, {
                                       "_id": 0}).sort("created_at", DESCENDING).limit(limit)
        return list(cursor)

    def save_rainfall_event(self, event_id: str, name: str, rain_mmhr: List[float], timestamps_utc: List[str], **kwargs) -> str:
        doc = {"event_id": event_id, "name": name, "rain_mmhr": rain_mmhr,
               "timestamps_utc": timestamps_utc, "created_at": datetime.utcnow()}
        if rain_mmhr:
            doc["total_rainfall_mm"] = sum(rain_mmhr)
            doc["peak_intensity_mmhr"] = max(rain_mmhr)
            doc["duration_hours"] = len(rain_mmhr)
        for k, v in kwargs.items():
            if v is not None:
                doc[k] = v
        self.rainfall_events.replace_one(
            {"event_id": event_id}, doc, upsert=True)
        return event_id

    def get_rainfall_event(self, event_id: str) -> Optional[Dict]:
        return self.rainfall_events.find_one({"event_id": event_id}, {"_id": 0})

    def list_catchments(self, land_use: str = None) -> List[Dict]:
        query = {"land_use": land_use} if land_use else {}
        return list(self.catchments.find(query, {"_id": 0}))

    def list_rainfall_events(self, event_type: str = None, min_return_period: int = None) -> List[Dict]:
        query = {}
        if event_type:
            query["event_type"] = event_type
        if min_return_period:
            query["return_period_years"] = {"$gte": min_return_period}
        return list(self.rainfall_events.find(query, {"_id": 0}))

    def close(self):
        self.client.close()
