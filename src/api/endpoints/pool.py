from fastapi import APIRouter

from src.dependencies import get_session_pool
from src.schemas.pool import PoolStatusResponse

router = APIRouter(prefix="/api/pool", tags=["pool"])


@router.get("/status", response_model=PoolStatusResponse)
async def pool_status() -> PoolStatusResponse:
    pool = await get_session_pool()
    return PoolStatusResponse(**pool.status())
