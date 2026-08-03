from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from tests.conftest import make_mock_user


class TestUserResolveEndpoint:
    async def test_success(self, test_client: AsyncClient) -> None:
        with patch(
            "src.services.telegram._resolve_entity",
            new=AsyncMock(return_value=make_mock_user(user_id=811277638, username="krivondulia")),
        ):
            response = await test_client.get("/api/users/krivondulia/resolve")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 811277638
        assert data["username"] == "krivondulia"

    async def test_not_found_returns_404(self, test_client: AsyncClient) -> None:
        with patch(
            "src.services.telegram._resolve_entity",
            new=AsyncMock(side_effect=ValueError("Could not resolve Telegram entity by numeric id 1: no access_hash")),
        ):
            response = await test_client.get("/api/users/1/resolve")
        assert response.status_code == 404
