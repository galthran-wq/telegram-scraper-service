from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from httpx import AsyncClient


async def test_pool_status_returns_snapshot(client: AsyncClient) -> None:
    snapshot = {
        "alive": 2,
        "configured": 3,
        "sessions": [
            {"name": "acc1.stringsession", "connected": True},
            {"name": "acc2.stringsession", "connected": False},
        ],
        "recent_evictions": [
            {"ts": "2026-05-12T10:00:00+00:00", "session": "dead.session", "reason": "AuthKeyUnregisteredError"}
        ],
        "rescan_interval": 30,
    }
    pool = MagicMock()
    pool.status = MagicMock(return_value=snapshot)
    with patch("src.api.endpoints.pool.get_session_pool", new_callable=AsyncMock, return_value=pool):
        response = await client.get("/api/pool/status")

    assert response.status_code == 200
    data = response.json()
    assert data["alive"] == 2
    assert data["configured"] == 3
    assert len(data["sessions"]) == 2
    assert data["recent_evictions"][0]["reason"] == "AuthKeyUnregisteredError"
    assert data["rescan_interval"] == 30
