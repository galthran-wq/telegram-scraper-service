from fastapi import APIRouter

from src.dependencies import get_session_pool
from src.schemas.pool import PoolRescanResponse, PoolStatusResponse

router = APIRouter(prefix="/api/pool", tags=["pool"])


@router.get("/status", response_model=PoolStatusResponse)
async def pool_status() -> PoolStatusResponse:
    pool = await get_session_pool()
    return PoolStatusResponse(**pool.status())


@router.post("/rescan", response_model=PoolRescanResponse)
async def pool_rescan() -> PoolRescanResponse:
    pool = await get_session_pool()
    added = await pool.rescan()
    return PoolRescanResponse(added=added, alive=len(pool._clients))
