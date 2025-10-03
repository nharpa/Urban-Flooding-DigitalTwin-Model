from digital_twin.database import database_utils


def main() -> int:
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
