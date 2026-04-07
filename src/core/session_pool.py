import asyncio
import random
from itertools import cycle
from pathlib import Path
from urllib.parse import urlparse

import structlog
from telethon import TelegramClient

from src.config import settings

logger = structlog.get_logger()


def _parse_proxy(proxy_url: str) -> tuple:
    from python_socks import ProxyType

    parsed = urlparse(proxy_url)
    scheme = parsed.scheme.lower()
    scheme_map = {"http": ProxyType.HTTP, "https": ProxyType.HTTP, "socks5": ProxyType.SOCKS5, "socks4": ProxyType.SOCKS4}
    proxy_type = scheme_map.get(scheme)
    if proxy_type is None:
        raise ValueError(f"Unsupported proxy scheme: {scheme}")
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Proxy URL must include host and port: {proxy_url}")
    return (proxy_type, parsed.hostname, parsed.port, True, parsed.username, parsed.password)


class SessionPool:
    def __init__(self) -> None:
        self._clients: list[TelegramClient] = []
        self._cycle: cycle[TelegramClient] | None = None
        self._lock = asyncio.Lock()
        self._proxy: tuple | None = None
        self._session_paths: dict[TelegramClient, str] = {}

    async def init(self) -> None:
        if settings.proxy:
            self._proxy = _parse_proxy(settings.proxy)
            logger.info("proxy_configured", scheme=settings.proxy.split("://")[0])

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
            client = await self._connect(session_path)
            if client:
                self._clients.append(client)
                self._session_paths[client] = session_path
                logger.info("session_loaded", session=session_file.name)

        if self._clients:
            random.shuffle(self._clients)
            self._cycle = cycle(self._clients)
            logger.info("session_pool_ready", count=len(self._clients))

    async def _connect(self, session_path: str) -> TelegramClient | None:
        client = TelegramClient(session_path, settings.telegram_api_id, settings.telegram_api_hash, proxy=self._proxy)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning("session_not_authorized", session=Path(session_path).name)
                await client.disconnect()
                return None
        except Exception:
            await client.disconnect()
            raise
        return client

    async def reconnect(self, client: TelegramClient) -> bool:
        session_path = self._session_paths.get(client)
        if not session_path:
            return False
        try:
            await client.disconnect()
        except Exception:
            pass
        try:
            await client.connect()
            if await client.is_user_authorized():
                logger.info("session_reconnected", session=Path(session_path).name)
                return True
        except Exception as e:
            logger.warning("reconnect_failed", session=Path(session_path).name, error=str(e))
        return False

    async def close(self) -> None:
        for client in self._clients:
            await client.disconnect()
        self._clients.clear()
        self._session_paths.clear()
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
            self._session_paths.pop(client, None)
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
