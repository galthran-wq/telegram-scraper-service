from fastapi import APIRouter

from src.api.endpoints import channels, health, search

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(channels.router)
router.include_router(search.router)
