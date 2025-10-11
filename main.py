from fastapi import FastAPI
from digital_twin.services.realtime_monitor import RealTimeFloodMonitor
from contextlib import asynccontextmanager
from api.v1.routes import api_router
import argparse
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor = RealTimeFloodMonitor()
    # Only start periodic monitoring if not disabled
    if not os.getenv("DISABLE_MONITORING", "").lower() in ["true", "1", "yes"]:
        monitor.start_periodic_monitoring()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="digital-twin-service", lifespan=lifespan)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Urban Flooding Digital Twin Service")
    parser.add_argument("--no-monitoring", action="store_true",
                        help="Disable periodic monitoring background process")

    args = parser.parse_args()

    # Set environment variable to disable monitoring if requested
    if args.no_monitoring:
        os.environ["DISABLE_MONITORING"] = "true"

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
