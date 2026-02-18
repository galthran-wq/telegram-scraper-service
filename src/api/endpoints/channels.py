import structlog
from fastapi import APIRouter, HTTPException, Query

from src.core.retry import with_retry
from src.schemas.telegram import (
    ChannelFullInfo,
    ChannelPhotosResponse,
    ChannelPostsResponse,
    PostCommentsResponse,
)
from src.services.telegram import (
    get_channel_info,
    get_channel_photos,
    get_channel_posts,
    get_post_comments,
    search_channel_messages,
    search_comments,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/{channel}/info", response_model=ChannelFullInfo)
async def channel_info(channel: str) -> ChannelFullInfo:
    try:
        info = await with_retry(get_channel_info, channel)
        return ChannelFullInfo(**info)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("channel_info_error", channel=channel, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{channel}/posts", response_model=ChannelPostsResponse)
async def channel_posts(
    channel: str,
    offset_id: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> ChannelPostsResponse:
    try:
        messages = await with_retry(get_channel_posts, channel, offset_id=offset_id, limit=limit)
        return ChannelPostsResponse(messages=messages, count=len(messages))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("channel_posts_error", channel=channel, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{channel}/posts/{post_id}/comments", response_model=PostCommentsResponse)
async def post_comments(
    channel: str,
    post_id: int,
    offset_id: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> PostCommentsResponse:
    try:
        messages = await with_retry(get_post_comments, channel, post_id, offset_id=offset_id, limit=limit)
        return PostCommentsResponse(messages=messages, count=len(messages))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("post_comments_error", channel=channel, post_id=post_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{channel}/photos", response_model=ChannelPhotosResponse)
async def channel_photos(
    channel: str,
    offset_id: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
) -> ChannelPhotosResponse:
    try:
        messages = await with_retry(get_channel_photos, channel, offset_id=offset_id, limit=limit)
        return ChannelPhotosResponse(messages=messages, count=len(messages))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("channel_photos_error", channel=channel, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{channel}/search", response_model=ChannelPostsResponse)
async def channel_search(
    channel: str,
    q: str = Query(..., min_length=1),
    offset_id: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> ChannelPostsResponse:
    try:
        messages = await with_retry(search_channel_messages, channel, q, offset_id=offset_id, limit=limit)
        return ChannelPostsResponse(messages=messages, count=len(messages))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("channel_search_error", channel=channel, query=q, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{channel}/comments/search", response_model=ChannelPostsResponse)
async def channel_comments_search(
    channel: str,
    q: str = Query(..., min_length=1),
    offset_id: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> ChannelPostsResponse:
    try:
        messages = await with_retry(search_comments, channel, q, offset_id=offset_id, limit=limit)
        return ChannelPostsResponse(messages=messages, count=len(messages))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("channel_comments_search_error", channel=channel, query=q, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
