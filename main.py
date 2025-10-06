from fastapi import FastAPI
from digital_twin.services.realtime_monitor import RealTimeFloodMonitor
from contextlib import asynccontextmanager
from api.v1.routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor = RealTimeFloodMonitor()
    monitor.start_periodic_monitoring()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="digital-twin-service", lifespan=lifespan)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
