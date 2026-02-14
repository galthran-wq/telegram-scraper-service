from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.main import app
from telethon.tl.types import Channel, PeerChannel, User


class AsyncIter:
    def __init__(self, items: list) -> None:  # type: ignore[type-arg]
        self._items = items
        self._index = 0

    def __aiter__(self) -> "AsyncIter":
        return self

    async def __anext__(self) -> object:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


def make_mock_user(
    user_id: int = 123, first_name: str = "Test", last_name: str = "User", username: str = "testuser"
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = first_name
    user.last_name = last_name
    user.username = username
    return user


def make_mock_channel(
    channel_id: int = 456, title: str = "Test Channel", username: str = "testchannel", access_hash: int = 789
) -> MagicMock:
    ch = MagicMock(spec=Channel)
    ch.id = channel_id
    ch.title = title
    ch.username = username
    ch.access_hash = access_hash
    return ch


def make_mock_message(
    msg_id: int = 1,
    text: str = "test message",
    date: datetime | None = None,
    views: int = 100,
    forwards: int = 10,
    replies_count: int | None = 5,
    sender: MagicMock | None = None,
    chat: MagicMock | None = None,
    media: object | None = None,
    peer_id: PeerChannel | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.date = date or datetime(2025, 1, 1, tzinfo=UTC)
    msg.views = views
    msg.forwards = forwards
    msg.replies = MagicMock(replies=replies_count) if replies_count is not None else None
    msg.edit_date = None
    msg.grouped_id = None
    msg.sender = sender or make_mock_user()
    msg.chat = chat or make_mock_channel()
    msg.media = media
    msg.peer_id = peer_id or PeerChannel(channel_id=456)
    msg._finish_init = MagicMock()
    return msg


@pytest.fixture
def mock_messages() -> list[MagicMock]:
    return [
        make_mock_message(msg_id=100, text="Post 1"),
        make_mock_message(msg_id=99, text="Post 2"),
        make_mock_message(msg_id=98, text="Post 3"),
    ]


@pytest.fixture
def mock_client(mock_messages: list[MagicMock]) -> AsyncMock:
    client = AsyncMock()
    client.get_entity = AsyncMock(return_value=MagicMock())
    client.iter_messages = MagicMock(return_value=AsyncIter(mock_messages))
    return client


@pytest.fixture
def mock_pool(mock_client: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.get_next = AsyncMock(return_value=mock_client)
    pool.remove_client = AsyncMock()
    pool.available = True
    return pool


@pytest_asyncio.fixture
async def test_client(mock_pool: MagicMock) -> AsyncIterator[AsyncClient]:
    with (
        patch("src.core.retry.get_session_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("src.dependencies.init_session_pool", new_callable=AsyncMock),
        patch("src.dependencies.close_session_pool", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    with (
        patch("src.dependencies.init_session_pool", new_callable=AsyncMock),
        patch("src.dependencies.close_session_pool", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
