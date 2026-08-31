from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["mock", "discord", "zalo", "messenger"]


class LinkCodeRequest(BaseModel):
    platform: Platform


class LinkCodePublic(BaseModel):
    platform: Platform
    code: str
    expires_at: datetime


class LinkIdentityRequest(BaseModel):
    external_user_id: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=8, max_length=100)


class ChannelBindRequest(BaseModel):
    channel_id: str = Field(min_length=1, max_length=255)
    course_id: int
    privacy_mode: Literal["MENTION_ONLY", "PRIVATE_ONLY"] = "MENTION_ONLY"


class ChannelBindingPublic(BaseModel):
    id: int
    platform: Platform
    channel_id: str
    course_id: int
    privacy_mode: str
    is_active: bool


class MessageEnvelope(BaseModel):
    external_event_id: str = Field(min_length=1, max_length=255)
    external_user_id: str = Field(min_length=1, max_length=255)
    channel_id: str = Field(min_length=1, max_length=255)
    thread_id: str = Field(default="", max_length=255)
    is_group: bool
    mentioned_nova: bool = False
    text: str = Field(min_length=1, max_length=4000)
    timestamp: datetime


class WebhookAccepted(BaseModel):
    accepted: bool
    duplicate: bool
    event_id: int


class EventAuditPublic(BaseModel):
    id: int
    platform: str
    external_event_id: str
    channel_id: str
    status: str
    retry_count: int
    error: str | None
    created_at: datetime
