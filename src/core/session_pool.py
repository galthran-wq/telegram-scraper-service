import asyncio
import base64
import contextlib
import ipaddress
import os
import random
import struct
from collections import deque
from datetime import UTC, datetime
from itertools import cycle
from pathlib import Path
from urllib.parse import urlparse

import structlog
from telethon import TelegramClient
from telethon.sessions import StringSession

from src.config import settings

logger = structlog.get_logger()

STRING_SESSION_EXT = ".stringsession"
SQLITE_SESSION_EXT = ".session"
EVICTION_LOG_SIZE = 20
AUTH_KEY_BYTES = 256
DC_IP = {
    1: "149.154.175.53",
    2: "149.154.167.51",
    3: "149.154.175.100",
    4: "149.154.167.91",
    5: "91.108.56.130",
}


def encode_string_session(auth_key_hex: str, dc_id: int) -> str:
    if dc_id not in DC_IP:
        raise ValueError(f"Unknown dc_id: {dc_id}")
    auth_key = bytes.fromhex(auth_key_hex)
    if len(auth_key) != AUTH_KEY_BYTES:
        raise ValueError(f"auth_key must be exactly {AUTH_KEY_BYTES} bytes ({AUTH_KEY_BYTES * 2} hex chars)")
    ip = ipaddress.ip_address(DC_IP[dc_id]).packed
    payload = struct.pack(f">B{len(ip)}sH256s", dc_id, ip, 443, auth_key)
    return "1" + base64.urlsafe_b64encode(payload).decode("ascii")


def _parse_proxy(proxy_url: str) -> tuple[object, ...]:
    from python_socks import ProxyType

    parsed = urlparse(proxy_url)
    scheme = parsed.scheme.lower()
    scheme_map = {
        "http": ProxyType.HTTP,
        "https": ProxyType.HTTP,
        "socks5": ProxyType.SOCKS5,
        "socks4": ProxyType.SOCKS4,
    }
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
        self._proxy: tuple[object, ...] | None = None
        self._session_paths: dict[TelegramClient, str] = {}
        self._evictions: deque[dict[str, str]] = deque(maxlen=EVICTION_LOG_SIZE)
        self._rescan_task: asyncio.Task[None] | None = None
        self._inflight_rescan_paths: set[str] = set()

    async def init(self) -> None:
        if settings.proxy:
            self._proxy = _parse_proxy(settings.proxy)
            logger.info("proxy_configured", scheme=settings.proxy.split("://")[0])

        sessions_dir = Path(settings.sessions_dir)
        if not sessions_dir.exists():
            logger.warning("sessions_dir_not_found", path=str(sessions_dir))
            return

        session_paths = self._discover_session_paths(sessions_dir)
        if not session_paths:
            logger.warning("no_sessions_found", path=str(sessions_dir))

        for session_path in session_paths:
            await self._load(session_path)

        if self._clients:
            random.shuffle(self._clients)
            self._cycle = cycle(self._clients)
            logger.info("session_pool_ready", count=len(self._clients))

        if settings.sessions_rescan_interval > 0:
            self._rescan_task = asyncio.create_task(self._rescan_loop())

    def _discover_session_paths(self, sessions_dir: Path) -> list[str]:
        sqlite_paths = [str(p.with_suffix("")) for p in sessions_dir.glob(f"*{SQLITE_SESSION_EXT}")]
        string_paths = [str(p) for p in sessions_dir.glob(f"*{STRING_SESSION_EXT}")]
        return sorted(sqlite_paths + string_paths)

    async def _load(self, session_path: str) -> TelegramClient | None:
        client = await self._connect(session_path)
        if not client:
            return None
        self._clients.append(client)
        self._session_paths[client] = session_path
        logger.info("session_loaded", session=Path(session_path).name)
        return client

    async def _connect(self, session_path: str) -> TelegramClient | None:
        if session_path.endswith(STRING_SESSION_EXT):
            try:
                session_str = Path(session_path).read_text(encoding="utf-8").strip()
            except OSError as e:
                logger.warning("string_session_read_failed", session=Path(session_path).name, error=str(e))
                return None
            if not session_str:
                logger.warning("string_session_empty", session=Path(session_path).name)
                return None
            session: StringSession | str = StringSession(session_str)
        else:
            session = session_path

        client = TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash, proxy=self._proxy)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning("session_not_authorized", session=Path(session_path).name)
                await client.disconnect()
                return None
        except Exception as e:
            logger.warning("session_connect_failed", session=Path(session_path).name, error=str(e))
            with contextlib.suppress(Exception):
                await client.disconnect()
            return None
        return client

    async def add_string_session(self, name: str, session_str: str) -> dict[str, object]:
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return {"error": "invalid name"}
        session_str = session_str.strip()
        if not session_str:
            return {"error": "empty session string"}

        sessions_dir = Path(settings.sessions_dir)
        sessions_dir.mkdir(parents=True, exist_ok=True)
        dest = sessions_dir / f"{name}{STRING_SESSION_EXT}"
        tmp = dest.with_suffix(STRING_SESSION_EXT + ".tmp")

        async with self._lock:
            if str(dest) in self._session_paths.values() or str(dest) in self._inflight_rescan_paths:
                return {"error": f"session '{name}' already loaded"}
            if dest.exists():
                return {"error": f"session file '{dest.name}' already exists"}
            tmp.write_text(session_str + "\n", encoding="utf-8")
            os.replace(tmp, dest)
            self._inflight_rescan_paths.add(str(dest))

        try:
            client = await self._connect(str(dest))
            if not client:
                with contextlib.suppress(OSError):
                    dest.unlink()
                return {"error": "session failed to authorize"}
            try:
                me = await client.get_me()
                phone = getattr(me, "phone", None)
                user_id = getattr(me, "id", None)
            except Exception:
                logger.warning("get_me_failed", session=name)
                phone = None
                user_id = None
        finally:
            async with self._lock:
                self._inflight_rescan_paths.discard(str(dest))

        async with self._lock:
            self._clients.append(client)
            self._session_paths[client] = str(dest)
            self._cycle = cycle(self._clients)
            logger.info("session_added", session=dest.name, count=len(self._clients))

        return {"name": name, "phone": phone, "user_id": user_id}

    async def rescan(self) -> int:
        sessions_dir = Path(settings.sessions_dir)
        if not sessions_dir.exists():
            return 0

        async with self._lock:
            known = set(self._session_paths.values())
            discovered = set(self._discover_session_paths(sessions_dir))
            new_paths = sorted(discovered - known - self._inflight_rescan_paths)
            self._inflight_rescan_paths |= set(new_paths)

        connected: list[tuple[str, TelegramClient]] = []
        try:
            for session_path in new_paths:
                client = await self._connect(session_path)
                if client:
                    connected.append((session_path, client))
        finally:
            async with self._lock:
                self._inflight_rescan_paths -= set(new_paths)

        if not connected:
            return 0

        async with self._lock:
            for session_path, client in connected:
                self._clients.append(client)
                self._session_paths[client] = session_path
                logger.info("session_loaded", session=Path(session_path).name)
            self._cycle = cycle(self._clients)
            logger.info("session_pool_rescanned", added=len(connected), total=len(self._clients))
        return len(connected)

    async def _rescan_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.sessions_rescan_interval)
                await self.rescan()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("rescan_loop_error")

    async def reconnect(self, client: TelegramClient) -> bool:
        session_path = self._session_paths.get(client)
        if not session_path:
            return False
        with contextlib.suppress(Exception):
            await client.disconnect()
        try:
            await client.connect()
            if await client.is_user_authorized():
                logger.info("session_reconnected", session=Path(session_path).name)
                return True
        except Exception as e:
            logger.warning("reconnect_failed", session=Path(session_path).name, error=str(e))
        return False

    async def close(self) -> None:
        if self._rescan_task:
            self._rescan_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._rescan_task
            self._rescan_task = None
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

    async def remove_client(self, client: TelegramClient, reason: str = "unknown") -> None:
        async with self._lock:
            if client not in self._clients:
                return
            session_path = self._session_paths.get(client, "")
            session_name = Path(session_path).name if session_path else "unknown"
            self._clients.remove(client)
            self._session_paths.pop(client, None)
            if self._clients:
                self._cycle = cycle(self._clients)
            else:
                self._cycle = None
            remaining = len(self._clients)
            self._evictions.append(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "session": session_name,
                    "reason": reason,
                }
            )
        with contextlib.suppress(Exception):
            await client.disconnect()
        logger.warning("session_removed", session=session_name, reason=reason, remaining=remaining)

    def status(self) -> dict[str, object]:
        sessions_dir = Path(settings.sessions_dir)
        configured = len(self._discover_session_paths(sessions_dir)) if sessions_dir.exists() else 0
        sessions = []
        for client, path in self._session_paths.items():
            try:
                connected = client.is_connected()
            except Exception:
                connected = False
            sessions.append({"name": Path(path).name, "connected": bool(connected)})
        return {
            "alive": len(self._clients),
            "configured": configured,
            "sessions": sessions,
            "recent_evictions": list(self._evictions),
            "rescan_interval": settings.sessions_rescan_interval,
        }

    @property
    def available(self) -> bool:
        return len(self._clients) > 0
