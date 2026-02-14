import structlog
from fastapi import APIRouter, HTTPException, Query

from src.core.retry import with_retry
from src.schemas.telegram import SearchChannelsResponse, SearchPostsResponse
from src.services.telegram import search_channels, search_posts

logger = structlog.get_logger()

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/posts", response_model=SearchPostsResponse)
async def search_posts_endpoint(
    tag: str = Query(..., min_length=1),
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=100),
) -> SearchPostsResponse:
    try:
        messages, next_cursor = await with_retry(search_posts, tag, cursor=cursor, limit=limit)
        return SearchPostsResponse(messages=messages, next_cursor=next_cursor, count=len(messages))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("search_posts_error", tag=tag, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/channels", response_model=SearchChannelsResponse)
async def search_channels_endpoint(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
) -> SearchChannelsResponse:
    try:
        channels = await with_retry(search_channels, q, limit=limit)
        return SearchChannelsResponse(channels=channels, count=len(channels))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("search_channels_error", query=q, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
