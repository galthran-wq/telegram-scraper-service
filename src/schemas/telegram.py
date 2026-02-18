from datetime import datetime

from pydantic import BaseModel


class SenderInfo(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    title: str | None = None


class ChannelInfo(BaseModel):
    id: int
    title: str | None = None
    username: str | None = None


class MediaInfo(BaseModel):
    type: str


class MessageSchema(BaseModel):
    id: int
    date: datetime | None = None
    text: str | None = None
    views: int | None = None
    forwards: int | None = None
    replies_count: int | None = None
    channel: ChannelInfo | None = None
    sender: SenderInfo | None = None
    media: MediaInfo | None = None
    edit_date: datetime | None = None
    grouped_id: int | None = None


class ChannelPostsResponse(BaseModel):
    messages: list[MessageSchema]
    count: int


class PostCommentsResponse(BaseModel):
    messages: list[MessageSchema]
    count: int


class SearchPostsResponse(BaseModel):
    messages: list[MessageSchema]
    next_cursor: str | None = None
    count: int


class ChannelSearchResult(BaseModel):
    id: int
    title: str | None = None
    username: str | None = None
    participants_count: int | None = None
    about: str | None = None


class SearchChannelsResponse(BaseModel):
    channels: list[ChannelSearchResult]
    count: int


class PhotoMessageSchema(MessageSchema):
    photo_base64: str


class ChannelPhotosResponse(BaseModel):
    messages: list[PhotoMessageSchema]
    count: int


class ProfilePhotoSchema(BaseModel):
    index: int
    date: datetime | None = None
    photo_base64: str


class UserProfilePhotosResponse(BaseModel):
    user_id: str
    photos: list[ProfilePhotoSchema]
    count: int


class ChannelFullInfo(BaseModel):
    id: int
    title: str | None = None
    username: str | None = None
    about: str | None = None
    participants_count: int | None = None
    photo_url: str | None = None
    linked_chat_id: int | None = None
    broadcast: bool = False
    megagroup: bool = False
