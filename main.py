from fastapi import FastAPI
from api.v1.routes import api_router

def create_app() -> FastAPI:
    app = FastAPI(title="digital-twin-service")
    app.include_router(api_router, prefix="/api/v1")
    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)