from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    UserBannedInChannelError,
    UserDeactivatedBanError,
)

from src.dependencies import get_session_pool

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from telethon import TelegramClient

logger = structlog.get_logger()

MAX_RETRIES = 3


async def with_retry(
    func: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    **kwargs: Any,
) -> Any:
    pool = await get_session_pool()
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        client: TelegramClient | None = await pool.get_next()
        if not client:
            logger.error("no_sessions", func=func.__name__)
            raise HTTPException(status_code=503, detail="No telegram sessions available")
        try:
            return await func(client, *args, **kwargs)
        except FloodWaitError as e:
            logger.warning("flood_wait", seconds=e.seconds, attempt=attempt, func=func.__name__)
            last_error = e
        except (UserDeactivatedBanError, AuthKeyUnregisteredError) as e:
            logger.error(
                "session_dead",
                error_type=type(e).__name__,
                error=str(e),
                attempt=attempt,
                func=func.__name__,
                sessions_remaining=len(pool._clients) - 1,
            )
            await pool.remove_client(client)
            last_error = e
        except UserBannedInChannelError as e:
            logger.warning("user_banned_in_channel", error=str(e), attempt=attempt, func=func.__name__)
            last_error = e
    if isinstance(last_error, FloodWaitError):
        raise HTTPException(status_code=429, detail=f"Rate limited, retry after {last_error.seconds}s")
    if isinstance(last_error, (UserDeactivatedBanError, AuthKeyUnregisteredError)):
        raise HTTPException(status_code=403, detail=f"All sessions deauthorized: {type(last_error).__name__}")
    if isinstance(last_error, UserBannedInChannelError):
        raise HTTPException(status_code=403, detail="Account banned in this channel")
    raise HTTPException(status_code=500, detail=str(last_error))
