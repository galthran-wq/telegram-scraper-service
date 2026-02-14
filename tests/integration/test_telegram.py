import os
from pathlib import Path

import pytest
from src.config import settings
from telethon import TelegramClient

SKIP_REASON = "TELEGRAM_API_ID and TELEGRAM_API_HASH env vars required"
skip_no_creds = pytest.mark.skipif(
    not os.getenv("TELEGRAM_API_ID") or not os.getenv("TELEGRAM_API_HASH"),
    reason=SKIP_REASON,
)

pytestmark = [pytest.mark.integration, skip_no_creds]

TEST_CHANNEL = os.getenv("TEST_CHANNEL", "durov")


def _get_session_path() -> str | None:
    sessions_dir = Path(settings.sessions_dir)
    if not sessions_dir.exists():
        return None
    files = sorted(sessions_dir.glob("*.session"))
    if not files:
        return None
    return str(files[0].with_suffix(""))


@pytest.fixture
async def tg_client() -> TelegramClient:  # type: ignore[misc]
    path = _get_session_path()
    if not path:
        pytest.skip("No session files found")
    c = TelegramClient(path, settings.telegram_api_id, settings.telegram_api_hash)
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        pytest.skip("Session not authorized")
    yield c  # type: ignore[misc]
    await c.disconnect()


class TestSessionPool:
    async def test_client_is_authorized(self, tg_client: TelegramClient) -> None:
        assert await tg_client.is_user_authorized()


class TestChannelPosts:
    async def test_fetch_posts(self, tg_client: TelegramClient) -> None:
        entity = await tg_client.get_entity(TEST_CHANNEL)
        messages = []
        async for msg in tg_client.iter_messages(entity, limit=5):
            messages.append(msg)
        assert len(messages) > 0

    async def test_post_has_expected_fields(self, tg_client: TelegramClient) -> None:
        entity = await tg_client.get_entity(TEST_CHANNEL)
        async for msg in tg_client.iter_messages(entity, limit=1):
            assert msg.id is not None
            assert msg.date is not None
            assert msg.text is not None or msg.media is not None
            break

    async def test_pagination_with_offset_id(self, tg_client: TelegramClient) -> None:
        entity = await tg_client.get_entity(TEST_CHANNEL)
        first_batch = []
        async for msg in tg_client.iter_messages(entity, limit=3):
            first_batch.append(msg)
        assert len(first_batch) == 3

        second_batch = []
        async for msg in tg_client.iter_messages(entity, limit=3, offset_id=first_batch[-1].id):
            second_batch.append(msg)
        assert len(second_batch) > 0
        assert second_batch[0].id < first_batch[-1].id


class TestPostComments:
    async def test_fetch_comments(self, tg_client: TelegramClient) -> None:
        entity = await tg_client.get_entity(TEST_CHANNEL)
        post_with_comments = None
        async for msg in tg_client.iter_messages(entity, limit=20):
            if msg.replies and msg.replies.replies > 0:
                post_with_comments = msg
                break

        if not post_with_comments:
            pytest.skip(f"No posts with comments found in {TEST_CHANNEL}")

        comments = []
        async for comment in tg_client.iter_messages(entity, reply_to=post_with_comments.id, limit=5):
            comments.append(comment)
        assert len(comments) > 0

    async def test_comment_has_sender(self, tg_client: TelegramClient) -> None:
        entity = await tg_client.get_entity(TEST_CHANNEL)
        async for msg in tg_client.iter_messages(entity, limit=20):
            if msg.replies and msg.replies.replies > 0:
                async for comment in tg_client.iter_messages(entity, reply_to=msg.id, limit=1):
                    assert comment.sender is not None or comment.from_id is not None
                    return
        pytest.skip(f"No posts with comments found in {TEST_CHANNEL}")


class TestSearchPosts:
    async def test_search_by_hashtag(self, tg_client: TelegramClient) -> None:
        from telethon.tl.functions.channels import SearchPostsRequest
        from telethon.tl.types import InputPeerEmpty

        try:
            r = await tg_client(SearchPostsRequest("#python", 0, InputPeerEmpty(), 0, 10))
        except Exception as e:
            pytest.skip(f"SearchPostsRequest not supported: {e}")

        assert hasattr(r, "messages")
        assert hasattr(r, "chats")

    async def test_search_returns_messages_with_peer_id(self, tg_client: TelegramClient) -> None:
        from telethon.tl.functions.channels import SearchPostsRequest
        from telethon.tl.types import InputPeerEmpty

        try:
            r = await tg_client(SearchPostsRequest("#news", 0, InputPeerEmpty(), 0, 5))
        except Exception as e:
            pytest.skip(f"SearchPostsRequest not supported: {e}")

        if not r.messages:
            pytest.skip("No results for #news")

        for msg in r.messages:
            assert msg.peer_id is not None


class TestSearchChannels:
    async def test_search_returns_results(self, tg_client: TelegramClient) -> None:
        from src.services.telegram import search_channels

        results = await search_channels(tg_client, "telegram", limit=5)
        assert len(results) > 0

    async def test_result_has_expected_fields(self, tg_client: TelegramClient) -> None:
        from src.services.telegram import search_channels

        results = await search_channels(tg_client, "telegram", limit=1)
        assert len(results) > 0
        ch = results[0]
        assert isinstance(ch["id"], int)
        assert ch["title"] is not None

    async def test_search_by_known_channel(self, tg_client: TelegramClient) -> None:
        from src.services.telegram import search_channels

        results = await search_channels(tg_client, TEST_CHANNEL, limit=10)
        assert len(results) > 0
        for ch in results:
            assert isinstance(ch["id"], int)
            assert ch["title"] is not None


class TestEndToEndSerialization:
    async def test_serialize_real_post(self, tg_client: TelegramClient) -> None:
        from src.services.telegram import _serialize_message

        entity = await tg_client.get_entity(TEST_CHANNEL)
        async for msg in tg_client.iter_messages(entity, limit=1):
            result = _serialize_message(msg)
            assert isinstance(result["id"], int)
            assert result["date"] is not None
            assert isinstance(result["text"], str)
            break

    async def test_full_channel_posts_flow(self, tg_client: TelegramClient) -> None:
        from src.services.telegram import get_channel_posts

        posts = await get_channel_posts(tg_client, TEST_CHANNEL, limit=3)
        assert len(posts) > 0
        for post in posts:
            assert "id" in post
            assert "date" in post
            assert "text" in post
