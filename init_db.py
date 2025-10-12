"""Database initialization script for Urban Flooding Digital Twin.

This module provides a simple database connectivity test and initialization
utility. It connects to MongoDB and lists available collections to verify
the database connection is working properly.
"""

from digital_twin.database import database_utils


def main() -> int:
    """Initialize and test MongoDB database connection.

    Attempts to connect to the MongoDB database, lists all available
    collections, and reports success or failure of the connection.

    Returns
    -------
    int
        Exit code: 0 for success, 1 for failure.
    """
    try:
        db = database_utils.FloodingDatabase()
        print("MongoDB initialization successful. Collections present:")
        for name in db.db.list_collection_names():
            print(f" - {name}")
        db.close()
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"Initialization failed: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
