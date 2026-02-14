from unittest.mock import AsyncMock, MagicMock, patch

from src.services.telegram import (
    _decode_cursor,
    _encode_cursor,
    _resolve_entity,
    _serialize_channel,
    _serialize_message,
    _serialize_sender,
    get_channel_posts,
    get_post_comments,
    search_posts,
)
from telethon.tl.types import PeerChannel

from tests.conftest import AsyncIter, make_mock_channel, make_mock_message, make_mock_user

FakeMediaPhoto = type("MessageMediaPhoto", (), {})


class TestSerializeSender:
    def test_user(self) -> None:
        user = make_mock_user(user_id=1, first_name="John", last_name="Doe", username="johndoe")
        result = _serialize_sender(user)
        assert result == {"id": 1, "first_name": "John", "last_name": "Doe", "username": "johndoe"}

    def test_channel(self) -> None:
        ch = make_mock_channel(channel_id=2, title="News", username="news")
        result = _serialize_sender(ch)
        assert result == {"id": 2, "title": "News", "username": "news"}

    def test_none(self) -> None:
        assert _serialize_sender(None) is None

    def test_unknown_type(self) -> None:
        assert _serialize_sender("unknown") is None


class TestSerializeChannel:
    def test_channel(self) -> None:
        ch = make_mock_channel(channel_id=1, title="Tech", username="tech")
        result = _serialize_channel(ch)
        assert result == {"id": 1, "title": "Tech", "username": "tech"}

    def test_none(self) -> None:
        assert _serialize_channel(None) is None

    def test_unknown_type(self) -> None:
        assert _serialize_channel("unknown") is None


class TestSerializeMessage:
    def test_basic(self) -> None:
        msg = make_mock_message(msg_id=42, text="hello", views=500, forwards=20)
        result = _serialize_message(msg)
        assert result["id"] == 42
        assert result["text"] == "hello"
        assert result["views"] == 500
        assert result["forwards"] == 20
        assert result["replies_count"] == 5
        assert result["sender"]["username"] == "testuser"
        assert result["channel"]["username"] == "testchannel"
        assert result["media"] is None

    def test_with_media(self) -> None:
        msg = make_mock_message(media=FakeMediaPhoto())
        result = _serialize_message(msg)
        assert result["media"]["type"] == "MessageMediaPhoto"

    def test_no_replies(self) -> None:
        msg = make_mock_message(replies_count=None)
        result = _serialize_message(msg)
        assert result["replies_count"] is None

    def test_empty_text(self) -> None:
        msg = make_mock_message(text=None)
        result = _serialize_message(msg)
        assert result["text"] == ""

    def test_sender_exception(self) -> None:
        msg = make_mock_message()
        type(msg).sender = property(lambda self: (_ for _ in ()).throw(Exception()))
        result = _serialize_message(msg)
        assert result["sender"] is None

    def test_chat_exception(self) -> None:
        msg = make_mock_message()
        type(msg).chat = property(lambda self: (_ for _ in ()).throw(Exception()))
        result = _serialize_message(msg)
        assert result["channel"] is None


class TestCursor:
    def test_encode_decode_roundtrip(self) -> None:
        cursor = _encode_cursor(100, 200, 300, 400)
        decoded = _decode_cursor(cursor)
        assert decoded == {"r": 100, "i": 200, "p": 300, "h": 400}

    def test_different_values(self) -> None:
        cursor = _encode_cursor(0, 0, 0, 0)
        decoded = _decode_cursor(cursor)
        assert decoded == {"r": 0, "i": 0, "p": 0, "h": 0}


class TestResolveEntity:
    async def test_numeric_string(self) -> None:
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value="resolved")
        await _resolve_entity(client, "12345")
        client.get_entity.assert_called_once_with(12345)

    async def test_username_string(self) -> None:
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value="resolved")
        await _resolve_entity(client, "testchannel")
        client.get_entity.assert_called_with("testchannel")


class TestGetChannelPosts:
    async def test_returns_serialized_messages(self) -> None:
        messages = [make_mock_message(msg_id=i, text=f"post {i}") for i in range(3)]
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value=MagicMock())
        client.iter_messages = MagicMock(return_value=AsyncIter(messages))

        result = await get_channel_posts(client, "testchannel", offset_id=0, limit=20)
        assert len(result) == 3
        assert result[0]["id"] == 0
        assert result[0]["text"] == "post 0"

    async def test_empty_channel(self) -> None:
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value=MagicMock())
        client.iter_messages = MagicMock(return_value=AsyncIter([]))

        result = await get_channel_posts(client, "testchannel")
        assert result == []


class TestGetPostComments:
    async def test_returns_serialized_comments(self) -> None:
        messages = [make_mock_message(msg_id=i, text=f"comment {i}") for i in range(2)]
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value=MagicMock())
        client.iter_messages = MagicMock(return_value=AsyncIter(messages))

        result = await get_post_comments(client, "testchannel", post_id=100)
        assert len(result) == 2
        assert result[1]["text"] == "comment 1"

    async def test_no_comments(self) -> None:
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value=MagicMock())
        client.iter_messages = MagicMock(return_value=AsyncIter([]))

        result = await get_post_comments(client, "testchannel", post_id=100)
        assert result == []


class TestSearchPosts:
    @patch("src.services.telegram.get_peer_id", return_value=-1000000000456)
    async def test_no_pagination(self, mock_gpi: MagicMock) -> None:
        mock_ch = make_mock_channel(channel_id=456, access_hash=789)
        messages = [make_mock_message(msg_id=i, chat=mock_ch, peer_id=PeerChannel(channel_id=456)) for i in range(2)]

        response = MagicMock()
        response.messages = messages
        response.chats = [mock_ch]
        response.users = [make_mock_user()]
        response.next_rate = None

        client = AsyncMock(return_value=response)
        result_msgs, next_cursor = await search_posts(client, "#test")
        assert len(result_msgs) == 2
        assert next_cursor is None

    @patch("src.services.telegram.get_peer_id", return_value=-1000000000456)
    async def test_with_pagination(self, mock_gpi: MagicMock) -> None:
        mock_ch = make_mock_channel(channel_id=456, access_hash=789)
        messages = [
            make_mock_message(msg_id=10, chat=mock_ch, peer_id=PeerChannel(channel_id=456)),
        ]

        response = MagicMock()
        response.messages = messages
        response.chats = [mock_ch]
        response.users = []
        response.next_rate = 42

        client = AsyncMock(return_value=response)
        result_msgs, next_cursor = await search_posts(client, "#test")
        assert len(result_msgs) == 1
        assert next_cursor is not None

        decoded = _decode_cursor(next_cursor)
        assert decoded["r"] == 42
        assert decoded["i"] == 10

    @patch("src.services.telegram.get_peer_id", return_value=-1000000000456)
    async def test_with_cursor_input(self, mock_gpi: MagicMock) -> None:
        mock_ch = make_mock_channel(channel_id=456, access_hash=789)
        cursor = _encode_cursor(10, 50, 456, 789)

        response = MagicMock()
        response.messages = []
        response.chats = [mock_ch]
        response.users = []
        response.next_rate = None

        client = AsyncMock(return_value=response)
        result_msgs, next_cursor = await search_posts(client, "#test", cursor=cursor)
        assert result_msgs == []
        assert next_cursor is None
