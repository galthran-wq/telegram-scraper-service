import base64
import json
from typing import Any

import structlog
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, SearchPostsRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import (
    Channel,
    InputPeerChannel,
    InputPeerEmpty,
    User,
)
from telethon.utils import get_peer_id

logger = structlog.get_logger()


def _serialize_sender(sender: Any) -> dict[str, Any] | None:
    if not sender:
        return None
    if isinstance(sender, User):
        return {
            "id": sender.id,
            "first_name": sender.first_name,
            "last_name": sender.last_name,
            "username": sender.username,
        }
    if isinstance(sender, Channel):
        return {
            "id": sender.id,
            "title": sender.title,
            "username": sender.username,
        }
    return None


def _serialize_channel(chat: Any) -> dict[str, Any] | None:
    if not chat:
        return None
    if isinstance(chat, Channel):
        return {
            "id": chat.id,
            "title": chat.title,
            "username": chat.username,
        }
    return None


def _serialize_message(message: Any) -> dict[str, Any]:
    try:
        sender = _serialize_sender(message.sender)
    except Exception:
        sender = None

    try:
        channel = _serialize_channel(message.chat)
    except Exception:
        channel = None

    return {
        "id": message.id,
        "date": message.date.isoformat() if message.date else None,
        "text": message.text or "",
        "views": message.views,
        "forwards": message.forwards,
        "replies_count": message.replies.replies if message.replies else None,
        "edit_date": message.edit_date.isoformat() if message.edit_date else None,
        "grouped_id": message.grouped_id,
        "sender": sender,
        "channel": channel,
        "media": {"type": type(message.media).__name__} if message.media else None,
    }


async def _resolve_entity(client: TelegramClient, channel: str) -> Any:
    try:
        channel_id = int(channel)
    except (ValueError, TypeError):
        return await client.get_entity(channel)
    return await client.get_entity(channel_id)


async def get_channel_posts(
    client: TelegramClient,
    channel: str,
    offset_id: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    logger.info("get_channel_posts", channel=channel, offset_id=offset_id, limit=limit)
    entity = await _resolve_entity(client, channel)
    messages = []
    async for message in client.iter_messages(entity, limit=limit, offset_id=offset_id):
        messages.append(_serialize_message(message))
    logger.info("get_channel_posts_done", channel=channel, count=len(messages))
    return messages


async def get_post_comments(
    client: TelegramClient,
    channel: str,
    post_id: int,
    offset_id: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    logger.info("get_post_comments", channel=channel, post_id=post_id, offset_id=offset_id, limit=limit)
    entity = await _resolve_entity(client, channel)
    messages = []
    async for message in client.iter_messages(entity, reply_to=post_id, limit=limit, offset_id=offset_id):
        messages.append(_serialize_message(message))
    logger.info("get_post_comments_done", channel=channel, post_id=post_id, count=len(messages))
    return messages


def _encode_cursor(offset_rate: int, offset_id: int, peer_id: int, peer_hash: int) -> str:
    data = {"r": offset_rate, "i": offset_id, "p": peer_id, "h": peer_hash}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, int]:
    return json.loads(base64.urlsafe_b64decode(cursor))  # type: ignore[no-any-return]


async def search_posts(
    client: TelegramClient,
    tag: str,
    cursor: str | None = None,
    limit: int = 100,
) -> tuple[list[dict[str, Any]], str | None]:
    if cursor:
        decoded = _decode_cursor(cursor)
        offset_rate = decoded["r"]
        offset_id = decoded["i"]
        offset_peer = InputPeerChannel(channel_id=decoded["p"], access_hash=decoded["h"])
    else:
        offset_rate = 0
        offset_id = 0
        offset_peer = InputPeerEmpty()

    logger.info("search_posts", tag=tag, offset_rate=offset_rate, offset_id=offset_id, limit=limit)
    r = await client(SearchPostsRequest(tag, offset_rate, offset_peer, offset_id, min(limit, 100)))

    entities = {get_peer_id(en): en for en in r.chats + r.users}
    messages = []
    for message in r.messages:
        message._finish_init(client, entities, message.peer_id)
        messages.append(_serialize_message(message))

    next_cursor = None
    next_rate = getattr(r, "next_rate", None)
    if next_rate is not None and r.messages:
        last_msg = r.messages[-1]
        last_peer_id = get_peer_id(last_msg.peer_id)
        last_chat = entities.get(last_peer_id)
        if last_chat and hasattr(last_chat, "access_hash"):
            next_cursor = _encode_cursor(next_rate, last_msg.id, last_chat.id, last_chat.access_hash)

    logger.info("search_posts_done", tag=tag, count=len(messages), has_next=next_cursor is not None)
    return messages, next_cursor


async def search_channels(
    client: TelegramClient,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    logger.info("search_channels", query=query, limit=limit)
    r = await client(SearchRequest(q=query, limit=limit))
    channels = []
    for chat in r.chats:
        if not isinstance(chat, Channel):
            continue
        channels.append(
            {
                "id": chat.id,
                "title": chat.title,
                "username": getattr(chat, "username", None),
                "participants_count": getattr(chat, "participants_count", None),
                "about": None,
            }
        )
    logger.info("search_channels_done", query=query, count=len(channels))
    return channels


async def search_channel_messages(
    client: TelegramClient,
    channel: str,
    query: str,
    offset_id: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    logger.info("search_channel_messages", channel=channel, query=query, offset_id=offset_id, limit=limit)
    entity = await _resolve_entity(client, channel)
    messages = []
    async for message in client.iter_messages(entity, search=query, limit=limit, offset_id=offset_id):
        messages.append(_serialize_message(message))
    logger.info("search_channel_messages_done", channel=channel, query=query, count=len(messages))
    return messages


async def search_comments(
    client: TelegramClient,
    channel: str,
    query: str,
    offset_id: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    logger.info("search_comments", channel=channel, query=query, offset_id=offset_id, limit=limit)
    entity = await _resolve_entity(client, channel)
    r = await client(GetFullChannelRequest(entity))
    linked_chat_id = getattr(r.full_chat, "linked_chat_id", None)
    if not linked_chat_id:
        raise ValueError(f"Channel {channel} has no linked discussion group")
    linked_entity = await client.get_entity(linked_chat_id)
    messages = []
    async for message in client.iter_messages(linked_entity, search=query, limit=limit, offset_id=offset_id):
        messages.append(_serialize_message(message))
    logger.info("search_comments_done", channel=channel, query=query, count=len(messages))
    return messages


async def get_channel_photos(
    client: TelegramClient,
    channel: str,
    offset_id: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get posts with photos, downloading each as base64."""
    logger.info("get_channel_photos", channel=channel, offset_id=offset_id, limit=limit)
    entity = await _resolve_entity(client, channel)
    results = []
    async for message in client.iter_messages(entity, limit=limit, offset_id=offset_id):
        if not message.media or type(message.media).__name__ != "MessageMediaPhoto":
            continue
        photo_bytes = await client.download_media(message, bytes)
        if not photo_bytes:
            continue
        results.append(
            {
                **_serialize_message(message),
                "photo_base64": base64.b64encode(photo_bytes).decode(),
            }
        )
    logger.info("get_channel_photos_done", channel=channel, count=len(results))
    return results


async def get_user_profile_photos(
    client: TelegramClient,
    user: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Download all profile photos for a user as base64."""
    logger.info("get_user_profile_photos", user=user, limit=limit)
    entity = await _resolve_entity(client, user)
    photos = await client.get_profile_photos(entity, limit=limit)
    results = []
    for i, photo in enumerate(photos):
        photo_bytes = await client.download_media(photo, bytes)
        if not photo_bytes:
            continue
        results.append(
            {
                "index": i,
                "date": photo.date.isoformat() if photo.date else None,
                "photo_base64": base64.b64encode(photo_bytes).decode(),
            }
        )
    logger.info("get_user_profile_photos_done", user=user, count=len(results))
    return results


async def get_channel_info(
    client: TelegramClient,
    channel: str,
) -> dict[str, Any]:
    logger.info("get_channel_info", channel=channel)
    entity = await _resolve_entity(client, channel)
    r = await client(GetFullChannelRequest(entity))
    chat = r.chats[0] if r.chats else entity
    full = r.full_chat
    result = {
        "id": chat.id,
        "title": getattr(chat, "title", None),
        "username": getattr(chat, "username", None),
        "about": getattr(full, "about", None),
        "participants_count": getattr(full, "participants_count", None),
        "linked_chat_id": getattr(full, "linked_chat_id", None),
        "broadcast": getattr(chat, "broadcast", False),
        "megagroup": getattr(chat, "megagroup", False),
    }
    logger.info("get_channel_info_done", channel=channel)
    return result
