import asyncio
import random
from itertools import cycle
from pathlib import Path

import structlog
from telethon import TelegramClient

from src.config import settings

logger = structlog.get_logger()


class SessionPool:
    def __init__(self) -> None:
        self._clients: list[TelegramClient] = []
        self._cycle: cycle[TelegramClient] | None = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        sessions_dir = Path(settings.sessions_dir)
        if not sessions_dir.exists():
            logger.warning("sessions_dir_not_found", path=str(sessions_dir))
            return

        session_files = sorted(sessions_dir.glob("*.session"))
        if not session_files:
            logger.warning("no_sessions_found", path=str(sessions_dir))
            return

        for session_file in session_files:
            session_path = str(session_file.with_suffix(""))
            client = TelegramClient(session_path, settings.telegram_api_id, settings.telegram_api_hash)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    logger.warning("session_not_authorized", session=session_file.name)
                    await client.disconnect()
                    continue
            except Exception:
                await client.disconnect()
                raise
            self._clients.append(client)
            logger.info("session_loaded", session=session_file.name)

        if self._clients:
            random.shuffle(self._clients)
            self._cycle = cycle(self._clients)
            logger.info("session_pool_ready", count=len(self._clients))

    async def close(self) -> None:
        for client in self._clients:
            await client.disconnect()
        self._clients.clear()
        self._cycle = None

    async def get_next(self) -> TelegramClient | None:
        async with self._lock:
            if not self._cycle:
                return None
            return next(self._cycle)

    async def remove_client(self, client: TelegramClient) -> None:
        async with self._lock:
            if client not in self._clients:
                return
            self._clients.remove(client)
            if self._clients:
                self._cycle = cycle(self._clients)
            else:
                self._cycle = None
            remaining = len(self._clients)
        await client.disconnect()
        logger.warning("session_removed", remaining=remaining)

    @property
    def available(self) -> bool:
        return len(self._clients) > 0
