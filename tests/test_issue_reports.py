from datetime import datetime
import pytest
from urban_flooding.persistence.database import FloodingDatabase


def _fresh_db():
    # Use a separate database name to avoid polluting primary data
    return FloodingDatabase(db_name="urban_flooding_dt_test")


def test_issue_lifecycle():
    db = _fresh_db()
    try:
        issue_id = db.create_issue_report(
            issue_type="Flooded road",
            description="Water over curb",
            latitude=-31.95,
            longitude=115.86,
            user_uid="tester123",
            display_name="Tester",
            email="tester@example.com",
            photo_urls=["http://example.com/img1.jpg"],
            notes="Initial submission"
        )
        doc = db.get_issue_report(issue_id)
        assert doc is not None
        assert doc["issue_id"] == issue_id
        assert doc["issue_type"] == "Flooded road"
        # Append notes
        ok = db.append_issue_notes(issue_id, "Investigating")
        assert ok
        updated = db.get_issue_report(issue_id)
        assert updated.get("notes") == "Investigating"
        # Add photos
        ok = db.add_issue_photos(issue_id, ["http://example.com/img2.jpg"])
        assert ok
        after_photos = db.get_issue_report(issue_id)
        assert len(after_photos["photo_urls"]) == 2
        # Near query
        near = db.find_issue_reports_near(
            longitude=115.86, latitude=-31.95, radius_meters=5000)
        assert any(r["issue_id"] == issue_id for r in near)
        # Stats
        stats = db.issue_report_statistics()
        assert stats["total_reports"] >= 1 and "by_type" in stats
    finally:
        # Drop the test database to keep clean state
        db.client.drop_database("urban_flooding_dt_test")
        db.close()
