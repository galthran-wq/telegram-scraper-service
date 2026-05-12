from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from src.config import settings
from src.core.session_pool import STRING_SESSION_EXT, _parse_proxy
from telethon import TelegramClient
from telethon.sessions import StringSession

MIN_LEN = 32
MAX_LEN = 8192
RESCAN_URL = "http://127.0.0.1:8000/api/pool/rescan"


async def _validate_and_write(name: str, session_str: str) -> dict:
    proxy = _parse_proxy(settings.proxy) if settings.proxy else None
    client = TelegramClient(
        StringSession(session_str), settings.telegram_api_id, settings.telegram_api_hash, proxy=proxy
    )
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return {"error": "session not authorized"}
        me = await client.get_me()
        phone = getattr(me, "phone", None)
        user_id = getattr(me, "id", None)
    finally:
        await client.disconnect()

    sessions_dir = Path(settings.sessions_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    dest = sessions_dir / f"{name}{STRING_SESSION_EXT}"
    if dest.exists():
        return {"error": f"session file '{dest.name}' already exists"}
    tmp = dest.with_suffix(STRING_SESSION_EXT + ".tmp")
    tmp.write_text(session_str + "\n", encoding="utf-8")
    os.replace(tmp, dest)
    return {"name": name, "phone": phone, "user_id": user_id, "path": str(dest)}


def _valid_name(name: str) -> bool:
    return bool(name) and "/" not in name and "\\" not in name and not name.startswith(".")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    if not _valid_name(args.name):
        print(json.dumps({"error": "invalid name"}), file=sys.stderr)
        return 2

    session_str = sys.stdin.readline().strip()
    if not session_str:
        print(json.dumps({"error": "empty stdin"}), file=sys.stderr)
        return 2
    if not MIN_LEN <= len(session_str) <= MAX_LEN:
        print(
            json.dumps({"error": f"session length {len(session_str)} out of bounds [{MIN_LEN}, {MAX_LEN}]"}),
            file=sys.stderr,
        )
        return 2

    try:
        result = asyncio.run(_validate_and_write(args.name, session_str))
    except Exception as e:
        print(json.dumps({"error": type(e).__name__}), file=sys.stderr)
        return 1

    if "error" in result:
        print(json.dumps(result), file=sys.stderr)
        return 1

    rescan_added: int | None = None
    try:
        req = urllib.request.Request(RESCAN_URL, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            rescan_added = json.loads(resp.read()).get("added")
    except (urllib.error.URLError, OSError, ValueError):
        rescan_added = None

    result["rescan_added"] = rescan_added
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
