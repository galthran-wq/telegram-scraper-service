import structlog
from fastapi import APIRouter, HTTPException, Query

from src.core.retry import with_retry
from src.schemas.telegram import UserProfilePhotosResponse
from src.services.telegram import get_user_profile_photos

logger = structlog.get_logger()

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/{user}/photos", response_model=UserProfilePhotosResponse)
async def user_photos(
    user: str,
    limit: int = Query(10, ge=1, le=50),
) -> UserProfilePhotosResponse:
    try:
        photos = await with_retry(get_user_profile_photos, user, limit=limit)
        return UserProfilePhotosResponse(user_id=user, photos=photos, count=len(photos))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error("user_photos_error", user=user, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
