from sqlalchemy import select

from app.academic_agent.agent import handle_chat
from app.config import get_settings
from app.connectors.discord.formatter import format_discord_reply
from app.connectors.discord.rest import DiscordRestClient
from app.db.models import AppUser, ExternalChannelBinding, ExternalIdentity
from app.db.session import AsyncSessionLocal


async def process_discord_outbox(payload: dict, rest: DiscordRestClient | None = None) -> None:
    if payload.get("platform") != "discord":
        raise ValueError("Discord worker chi xu ly payload platform=discord")
    settings = get_settings()
    client = rest or DiscordRestClient(settings.discord_bot_token or "")
    async with AsyncSessionLocal() as session:
        identity = (await session.execute(select(ExternalIdentity).where(
            ExternalIdentity.platform == "discord",
            ExternalIdentity.external_user_id == str(payload["external_user_id"]),
            ExternalIdentity.revoked_at.is_(None),
        ))).scalar_one_or_none()
        if identity is None:
            raise PermissionError("Discord identity da bi revoke hoac khong ton tai")
        user = await session.get(AppUser, identity.app_user_id)
        if user is None:
            raise PermissionError("App user khong ton tai")
        is_group = bool(payload.get("is_group"))
        course_id = None
        if is_group:
            binding = (await session.execute(select(ExternalChannelBinding).where(
                ExternalChannelBinding.platform == "discord",
                ExternalChannelBinding.channel_id == str(payload["channel_id"]),
                ExternalChannelBinding.is_active.is_(True),
            ))).scalar_one_or_none()
            if binding is None:
                raise PermissionError("Discord channel chua bind course")
            course_id = binding.course_id
        result = await handle_chat(
            session, user_id=user.id, user_role=user.role, is_admin=user.role == "ADMIN",
            message=str(payload["text"]), course_id=course_id, is_group=is_group,
        )
    chunks = format_discord_reply(result.answer, result.citations, settings.public_web_url)
    for index, chunk in enumerate(chunks):
        await client.send_message(
            str(payload["channel_id"]), chunk,
            str(payload["external_event_id"]) if index == 0 else None,
        )
