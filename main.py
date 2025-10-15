"""FastAPI application entry point for Urban Flooding Digital Twin service.

This module provides the main FastAPI application with integrated real-time monitoring
capabilities for urban flooding risk assessment. It includes lifecycle management for
background monitoring processes and configuration options 
for deployment.
"""

from fastapi import FastAPI
from digital_twin.services.realtime_monitor import RealTimeFloodMonitor
from contextlib import asynccontextmanager
from api.v1.routes import api_router
import argparse
import os
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan context manager.

    Manages the startup and shutdown of the real-time flood monitoring service.
    The monitoring can be disabled by setting the DISABLE_MONITORING environment
    variable to "true", "1", or "yes".

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.

    Yields
    ------
    None
        Control back to the application after startup.
    """
    monitor = RealTimeFloodMonitor()
    # Only start periodic monitoring if not disabled
    if not os.getenv("DISABLE_MONITORING", "").lower() in ["true", "1", "yes"]:
        monitor.start_periodic_monitoring()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Creates a FastAPI application with the digital twin service title,
    includes the lifespan event handler for background monitoring,
    and mounts the API router at the /api/v1 prefix.

    Returns
    -------
    FastAPI
        Configured FastAPI application instance ready for deployment.
    """
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

    uvicorn.run(app, host="0.0.0.0", port=8008)
