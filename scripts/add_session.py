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
from src.core.session_pool import AUTH_KEY_BYTES, DC_IP, STRING_SESSION_EXT, _parse_proxy, encode_string_session
from telethon import TelegramClient
from telethon.sessions import StringSession

MIN_LEN = 32
MAX_LEN = 8192
RESCAN_URL = "http://127.0.0.1:8000/api/pool/rescan"
HEX_CHARS = set("0123456789abcdefABCDEF")


def _is_auth_key_hex(s: str) -> bool:
    return len(s) == AUTH_KEY_BYTES * 2 and all(c in HEX_CHARS for c in s)


def _resolve_string_session(raw: str, dc: int | None) -> tuple[str, str | None]:
    if _is_auth_key_hex(raw):
        if dc is None:
            return "", "input looks like auth_key hex — pass --dc <1-5>"
        if dc not in DC_IP:
            return "", f"invalid --dc {dc}, expected one of {sorted(DC_IP)}"
        return encode_string_session(raw, dc), None
    if dc is not None:
        return "", "--dc only applies to auth_key hex input"
    return raw, None


async def _validate_and_write(name: str, session_str: str) -> dict:
    proxy = _parse_proxy(settings.proxy) if settings.proxy else None
    client = TelegramClient(
        StringSession(session_str),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        proxy=proxy,
        connection_retries=1,
        retry_delay=1,
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
    parser.add_argument("--dc", type=int, default=None, help="DC id (1-5) when feeding raw auth_key hex via stdin")
    args = parser.parse_args()

    if not _valid_name(args.name):
        print(json.dumps({"error": "invalid name"}), file=sys.stderr)
        return 2

    raw = sys.stdin.readline().strip()
    if not raw:
        print(json.dumps({"error": "empty stdin"}), file=sys.stderr)
        return 2
    if not MIN_LEN <= len(raw) <= MAX_LEN:
        print(json.dumps({"error": f"input length {len(raw)} out of bounds [{MIN_LEN}, {MAX_LEN}]"}), file=sys.stderr)
        return 2

    session_str, err = _resolve_string_session(raw, args.dc)
    if err:
        print(json.dumps({"error": err}), file=sys.stderr)
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
