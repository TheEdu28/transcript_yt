"""Registro de routers de la API v1."""

from fastapi import APIRouter

from app.api.v1.endpoints import config, exports, health, materials, videos

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(videos.router, prefix="/videos", tags=["videos"])
api_router.include_router(materials.router, prefix="/materials", tags=["materials"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(config.router, prefix="/settings", tags=["settings"])

