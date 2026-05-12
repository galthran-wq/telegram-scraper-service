from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.config import settings
from src.core.session_pool import STRING_SESSION_EXT, SessionPool

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "sessions_dir", str(tmp_path))
    monkeypatch.setattr(settings, "sessions_rescan_interval", 0)
    return tmp_path


def _make_authorized_client() -> AsyncMock:
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.is_connected = MagicMock(return_value=True)
    client.get_me = AsyncMock(return_value=MagicMock(id=42, phone="+10000000000"))
    return client


def _patch_clients(make: object = _make_authorized_client) -> object:
    return patch.multiple(
        "src.core.session_pool",
        TelegramClient=MagicMock(side_effect=lambda *a, **k: make()),  # type: ignore[operator]
        StringSession=MagicMock(side_effect=lambda *a, **k: MagicMock()),
    )


async def test_add_string_session_appends_and_cycles(sessions_dir: Path) -> None:
    pool = SessionPool()
    with _patch_clients():
        await pool.init()
        result_a = await pool.add_string_session("acc1", "x" * 100)
        result_b = await pool.add_string_session("acc2", "y" * 100)

    assert "error" not in result_a
    assert "error" not in result_b
    assert len(pool._clients) == 2
    assert (sessions_dir / f"acc1{STRING_SESSION_EXT}").exists()
    assert (sessions_dir / f"acc2{STRING_SESSION_EXT}").exists()

    seen = {await pool.get_next() for _ in range(4)}
    assert len(seen) == 2


async def test_add_string_session_rejects_unauthorized(sessions_dir: Path) -> None:
    def make_unauth() -> AsyncMock:
        c = AsyncMock()
        c.connect = AsyncMock()
        c.disconnect = AsyncMock()
        c.is_user_authorized = AsyncMock(return_value=False)
        return c

    pool = SessionPool()
    with _patch_clients(make=make_unauth):
        await pool.init()
        result = await pool.add_string_session("bad", "z" * 100)

    assert "error" in result
    assert len(pool._clients) == 0
    assert not (sessions_dir / f"bad{STRING_SESSION_EXT}").exists()


async def test_rescan_picks_up_new_stringsession_file(sessions_dir: Path) -> None:
    pool = SessionPool()
    with _patch_clients():
        await pool.init()
        assert len(pool._clients) == 0

        (sessions_dir / f"acc1{STRING_SESSION_EXT}").write_text("a" * 100 + "\n")
        added = await pool.rescan()

    assert added == 1
    assert len(pool._clients) == 1


async def test_rescan_skips_already_loaded(sessions_dir: Path) -> None:
    pool = SessionPool()
    with _patch_clients():
        await pool.init()
        (sessions_dir / f"acc1{STRING_SESSION_EXT}").write_text("a" * 100 + "\n")
        first = await pool.rescan()
        second = await pool.rescan()

    assert first == 1
    assert second == 0
    assert len(pool._clients) == 1


async def test_rescan_loop_cancelled_on_close(sessions_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sessions_rescan_interval", 1)
    pool = SessionPool()
    with _patch_clients():
        await pool.init()
        assert pool._rescan_task is not None
        assert not pool._rescan_task.done()
        await pool.close()

    assert pool._rescan_task is None


async def test_status_snapshot(sessions_dir: Path) -> None:
    pool = SessionPool()
    with _patch_clients():
        await pool.init()
        await pool.add_string_session("acc1", "a" * 100)
        await pool.add_string_session("acc2", "b" * 100)

    snap = pool.status()
    assert snap["alive"] == 2
    assert snap["configured"] == 2
    names = sorted(s["name"] for s in snap["sessions"])
    assert names == [f"acc1{STRING_SESSION_EXT}", f"acc2{STRING_SESSION_EXT}"]
    assert snap["recent_evictions"] == []


async def test_remove_client_records_eviction(sessions_dir: Path) -> None:
    pool = SessionPool()
    with _patch_clients():
        await pool.init()
        await pool.add_string_session("acc1", "a" * 100)

    client = pool._clients[0]
    await pool.remove_client(client, reason="AuthKeyUnregisteredError")

    snap = pool.status()
    assert snap["alive"] == 0
    assert len(snap["recent_evictions"]) == 1
    ev = snap["recent_evictions"][-1]
    assert ev["reason"] == "AuthKeyUnregisteredError"
    assert ev["session"] == f"acc1{STRING_SESSION_EXT}"


async def test_discover_session_paths_finds_both_kinds(sessions_dir: Path) -> None:
    (sessions_dir / "legacy.session").write_bytes(b"\x00")
    (sessions_dir / "new.stringsession").write_text("a" * 100 + "\n")
    pool = SessionPool()
    paths = pool._discover_session_paths(sessions_dir)
    assert any(p.endswith("legacy") for p in paths)
    assert any(p.endswith("new.stringsession") for p in paths)


@pytest.mark.parametrize(
    ("dc_id", "auth_key_byte"),
    [(1, "ab"), (2, "01"), (3, "7f"), (4, "ff"), (5, "5c")],
)
def test_encode_string_session_round_trip(dc_id: int, auth_key_byte: str) -> None:
    from src.core.session_pool import AUTH_KEY_BYTES, encode_string_session
    from telethon.sessions import StringSession

    auth_key_hex = auth_key_byte * AUTH_KEY_BYTES
    encoded = encode_string_session(auth_key_hex, dc_id=dc_id)
    assert encoded.startswith("1")
    session = StringSession(encoded)
    assert session.dc_id == dc_id
    assert session.auth_key is not None
    assert session.auth_key.key == bytes.fromhex(auth_key_hex)


def test_encode_string_session_rejects_bad_inputs() -> None:
    from src.core.session_pool import encode_string_session

    with pytest.raises(ValueError, match="Unknown dc_id"):
        encode_string_session("ab" * 256, dc_id=99)
    with pytest.raises(ValueError, match="exactly 256 bytes"):
        encode_string_session("abcd", dc_id=1)
    with pytest.raises(ValueError, match="non-hexadecimal"):
        encode_string_session("zz" * 256, dc_id=1)


def test_is_auth_key_hex_matches_512_hex_only() -> None:
    from scripts.add_session import _is_auth_key_hex

    assert _is_auth_key_hex("ab" * 256) is True
    assert _is_auth_key_hex("AB" * 256) is True
    assert _is_auth_key_hex("ab" * 255) is False
    assert _is_auth_key_hex("zz" * 256) is False
    assert _is_auth_key_hex("1" + "a" * 351) is False
