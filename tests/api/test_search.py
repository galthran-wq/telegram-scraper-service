from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from tests.conftest import AsyncIter, make_mock_message


class TestSearchEndpoint:
    async def test_success(self, test_client: AsyncClient, mock_pool: MagicMock) -> None:
        search_response = MagicMock()
        search_response.messages = [make_mock_message(msg_id=1)]
        search_response.chats = []
        search_response.users = []
        search_response.next_rate = None

        mock_client = AsyncMock(return_value=search_response)
        mock_client.get_entity = AsyncMock()
        mock_client.iter_messages = MagicMock(return_value=AsyncIter([]))
        mock_pool.get_next.return_value = mock_client

        response = await test_client.get("/api/search/posts", params={"tag": "#test"})
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "next_cursor" in data
        assert "count" in data

    async def test_missing_tag(self, test_client: AsyncClient) -> None:
        response = await test_client.get("/api/search/posts")
        assert response.status_code == 422
