import re
from datetime import datetime, timezone

from app.connectors.common.schemas import MessageEnvelope


def strip_bot_mention(content: str, bot_user_id: str) -> str:
    return re.sub(rf"<@!?{re.escape(bot_user_id)}>", "", content).strip()


def normalize_message_create(payload: dict, bot_user_id: str) -> MessageEnvelope | None:
    author = payload.get("author") or {}
    if author.get("bot") or str(author.get("id", "")) == bot_user_id:
        return None
    is_group = bool(payload.get("guild_id"))
    mentioned = any(str(user.get("id")) == bot_user_id for user in payload.get("mentions", []))
    if is_group and not mentioned:
        return None
    content = strip_bot_mention(str(payload.get("content", "")), bot_user_id)
    if not content:
        return None
    return MessageEnvelope(
        external_event_id=str(payload["id"]),
        external_user_id=str(author["id"]),
        channel_id=str(payload["channel_id"]),
        thread_id=str(payload.get("thread_id") or ""),
        is_group=is_group,
        mentioned_nova=mentioned or not is_group,
        text=content,
        timestamp=payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
    )


def discord_message_to_payload(message) -> dict:
    return {
        "id": str(message.id),
        "channel_id": str(message.channel.id),
        "guild_id": str(message.guild.id) if message.guild else None,
        "author": {"id": str(message.author.id), "bot": bool(message.author.bot)},
        "mentions": [{"id": str(user.id)} for user in message.mentions],
        "content": message.content,
        "timestamp": message.created_at.isoformat(),
        "thread_id": str(message.channel.id) if getattr(message.channel, "parent", None) else "",
    }
