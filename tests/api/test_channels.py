from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from telethon.errors import FloodWaitError

from tests.conftest import AsyncIter, make_mock_message


class TestChannelPostsEndpoint:
    async def test_success(self, test_client: AsyncClient) -> None:
        response = await test_client.get("/api/channels/testchannel/posts")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "count" in data
        assert data["count"] == 3

    async def test_with_pagination_params(self, test_client: AsyncClient) -> None:
        response = await test_client.get("/api/channels/testchannel/posts", params={"offset_id": 50, "limit": 10})
        assert response.status_code == 200

    async def test_invalid_limit(self, test_client: AsyncClient) -> None:
        response = await test_client.get("/api/channels/testchannel/posts", params={"limit": 200})
        assert response.status_code == 422

    async def test_negative_offset(self, test_client: AsyncClient) -> None:
        response = await test_client.get("/api/channels/testchannel/posts", params={"offset_id": -1})
        assert response.status_code == 422


class TestPostCommentsEndpoint:
    async def test_success(self, test_client: AsyncClient) -> None:
        response = await test_client.get("/api/channels/testchannel/posts/100/comments")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "count" in data
        assert data["count"] == 3

    async def test_with_pagination_params(self, test_client: AsyncClient) -> None:
        response = await test_client.get(
            "/api/channels/testchannel/posts/100/comments",
            params={"offset_id": 50, "limit": 5},
        )
        assert response.status_code == 200


class TestNoSessions:
    async def test_503_when_no_sessions(self, test_client: AsyncClient, mock_pool: MagicMock) -> None:
        mock_pool.get_next.return_value = None
        response = await test_client.get("/api/channels/testchannel/posts")
        assert response.status_code == 503
        assert "No telegram sessions" in response.json()["detail"]


class TestFloodWaitRetry:
    async def test_retries_on_flood_wait(self, test_client: AsyncClient, mock_pool: MagicMock) -> None:
        flood_error = FloodWaitError(request=None, capture=0)
        flood_error.seconds = 30

        success_client = AsyncMock()
        success_client.get_entity = AsyncMock(return_value=MagicMock())
        success_client.iter_messages = MagicMock(return_value=AsyncIter([make_mock_message(msg_id=1)]))

        fail_client = AsyncMock()
        fail_client.get_entity = AsyncMock(side_effect=flood_error)

        mock_pool.get_next.side_effect = [fail_client, success_client]

        response = await test_client.get("/api/channels/testchannel/posts")
        assert response.status_code == 200
        assert response.json()["count"] == 1

    async def test_429_when_all_retries_exhausted(self, test_client: AsyncClient, mock_pool: MagicMock) -> None:
        flood_error = FloodWaitError(request=None, capture=0)
        flood_error.seconds = 60

        fail_client = AsyncMock()
        fail_client.get_entity = AsyncMock(side_effect=flood_error)
        mock_pool.get_next.return_value = fail_client

        response = await test_client.get("/api/channels/testchannel/posts")
        assert response.status_code == 429
        assert "Rate limited" in response.json()["detail"]
