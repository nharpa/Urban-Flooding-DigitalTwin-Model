from fastapi import APIRouter
from api.v1.endpoints import simulate, risk

api_router = APIRouter()
api_router.include_router(simulate.router, prefix="", tags=["simulate"])
api_router.include_router(risk.router, prefix="", tags=["risk"])
