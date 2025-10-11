"""Database adapter (MongoDB) for Urban Flooding Digital Twin.

Migrated from legacy `database_v3.py`.
"""
from __future__ import annotations
from datetime import datetime
from typing import List, Dict, Optional
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from digital_twin.auth.config import settings
from digital_twin.database.database_schema import create_collections_with_validation, create_geospatial_indexes
from digital_twin.auth.config import settings


class FloodingDatabase:
    """MongoDB database operations class with spatial query support."""

    def __init__(self):
        """Initialize Mongo client and ensure `self.db` is a Database object.

        The previous implementation assigned `self.db = settings.MONGODB_NAME`
        when an env var was set, which yielded a plain string instead of a
        Database instance causing AttributeError on collection operations.
        """
        username = settings.MONGO_INITDB_ROOT_USERNAME
        password = settings.MONGO_INITDB_ROOT_PASSWORD
        base_uri = settings.MONGODB_URL
        db_name = settings.MONGODB_NAME
        # If username and password are set, inject them into the URI
        if username and password:
            self.uri = f"mongodb://{username}:{password}@{base_uri}"

        # Allow fast failure when server not present (e.g. during unit tests)
        self.client = MongoClient(self.uri, serverSelectionTimeoutMS=200)
        # Always obtain a Database object from the client
        if db_name is None:
            raise ValueError("MONGODB_NAME must be set and not None.")
        self.db = self.client[db_name]

        create_collections_with_validation(self.db)
        self.catchments: Collection = self.db["catchments"]
        self.simulations: Collection = self.db["simulations"]
        self.rainfall_events: Collection = self.db["rainfall_events"]
        self.issue_reports: Collection = self.db["issue_reports"]
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
        # Issue reports indexes
        try:
            self.issue_reports.create_index("issue_id", unique=True)
            self.issue_reports.create_index("issue_type")
            self.issue_reports.create_index("user.uid")
            # 2dsphere index for GeoJSON point
            self.issue_reports.create_index([("location", "2dsphere")])
        except Exception as e:  # pragma: no cover
            print(f"Issue reports index creation error: {e}")

    def save_catchment_full(self, catchment_data: Dict) -> str:
        """
        Upsert a full catchment record. Requires at least: catchment_id, name, C, A_km2, Qcap_m3s.
        Preserves all fields, including geometry and location/centroid.
        """
        required_fields = ["catchment_id", "name", "C", "A_km2", "Qcap_m3s"]
        for field in required_fields:
            if field not in catchment_data:
                raise ValueError(f"Missing required field: {field}")
        if "created_at" not in catchment_data:
            catchment_data["created_at"] = datetime.now()
        catchment_data["updated_at"] = datetime.now()
        self.catchments.replace_one(
            {"catchment_id": catchment_data["catchment_id"]}, catchment_data, upsert=True)
        return catchment_data["catchment_id"]

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

    def get_catchments_by_capacity(self, min_capacity: Optional[float] = None, max_capacity: Optional[float] = None) -> List[Dict]:
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
               "C": C, "A_km2": A_km2, "Qcap_m3s": Qcap_m3s, "k": k, "series": series, "max_risk": max_risk, "created_at": datetime.now()}
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
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cursor = self.simulations.find({"created_at": {"$gte": cutoff_date}}, {
                                       "_id": 0}).sort("created_at", DESCENDING).limit(limit)
        return list(cursor)

    def save_rainfall_event(self, event_id: str, name: str, rain_mmhr: List[float], timestamps_utc: List[str], **kwargs) -> str:
        doc = {"event_id": event_id, "name": name, "rain_mmhr": rain_mmhr,
               "timestamps_utc": timestamps_utc, "created_at": datetime.now()}
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

    def list_catchments(self, land_use: Optional[str] = None) -> List[Dict]:
        query = {"land_use": land_use} if land_use else {}
        return list(self.catchments.find(query, {"_id": 0}))

    def list_rainfall_events(self, event_type: Optional[str] = None, min_return_period: Optional[int] = None) -> List[Dict]:
        query = {}
        if event_type:
            query["event_type"] = event_type
        if min_return_period:
            query["return_period_years"] = {"$gte": min_return_period}
        return list(self.rainfall_events.find(query, {"_id": 0}))

    def close(self):
        self.client.close()

    # ---------------- Issue Reports -----------------
    def create_issue_report(self, issue_type: str, description: str, latitude: float, longitude: float, user_uid: str, display_name: Optional[str] = None, email: Optional[str] = None) -> str:
        """Create a new issue report and return its business key issue_id."""
        from uuid import uuid4
        issue_id = f"ISSUE_{uuid4().hex[:10]}"
        now = datetime.now()
        doc = {
            "issue_id": issue_id,
            "issue_type": issue_type,
            "description": description,
            "location": {"type": "Point", "coordinates": [float(longitude), float(latitude)]},
            "user": {"uid": user_uid, "display_name": display_name, "email": email},
            "created_at": now,
        }
        self.issue_reports.insert_one(doc)
        return issue_id

    def get_issue_report(self, issue_id: str) -> Optional[Dict]:
        doc = self.issue_reports.find_one({"issue_id": issue_id}, {"_id": 0})
        return doc

    def list_issue_reports(self, issue_type: str | None = None, user_uid: str | None = None, limit: int = 50, skip: int = 0) -> List[Dict]:
        query: Dict = {}
        if issue_type:
            query["issue_type"] = issue_type
        if user_uid:
            query["user.uid"] = user_uid
        cursor = self.issue_reports.find(query, {"_id": 0}).sort(
            "created_at", DESCENDING).skip(skip).limit(limit)
        return list(cursor)

    def find_issue_reports_near(self, longitude: float, latitude: float, radius_meters: int = 1000, limit: int = 50) -> List[Dict]:
        query = {
            "location": {
                "$near": {
                    "$geometry": {"type": "Point", "coordinates": [float(longitude), float(latitude)]},
                    "$maxDistance": int(radius_meters)
                }
            }
        }
        cursor = self.issue_reports.find(query, {"_id": 0}).limit(limit)
        return list(cursor)

    def issue_report_statistics(self) -> Dict:
        total = self.issue_reports.count_documents({})
        type_pipeline = [
            {"$group": {"_id": "$issue_type", "count": {"$sum": 1}}}]
        types: Dict[str, int] = {}
        for row in self.issue_reports.aggregate(type_pipeline):
            types[row["_id"]] = row["count"]
        return {"total_reports": total, "by_type": types}

    # Added to support tests expecting ability to append notes
    def append_issue_notes(self, issue_id: str, note: str) -> bool:
        """Append (store) a textual note to an issue report.

        Tests expect a plain string field 'notes' to equal the last value.
        We therefore just set/overwrite 'notes'.
        Returns True if modified.
        """
        res = self.issue_reports.update_one(
            {"issue_id": issue_id}, {"$set": {"notes": note}}
        )
        return res.modified_count > 0
