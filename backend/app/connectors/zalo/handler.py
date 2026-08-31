from sqlalchemy import select

from app.academic_agent.agent import handle_chat
from app.config import get_settings
from app.connectors.zalo.formatter import format_zalo_reply
from app.connectors.zalo.rest import ZaloOARestClient
from app.db.models import AppUser, ExternalChannelBinding, ExternalIdentity
from app.db.session import AsyncSessionLocal


async def process_zalo_outbox(payload: dict, rest: ZaloOARestClient | None = None) -> None:
    if payload.get("platform") != "zalo":
        raise ValueError("Zalo worker chi xu ly payload platform=zalo")
    settings = get_settings()
    if payload.get("is_group") and not settings.zalo_gmf_enabled:
        raise PermissionError("Zalo GMF chua duoc cap capability")
    client = rest or ZaloOARestClient(settings.zalo_oa_access_token or "")
    async with AsyncSessionLocal() as session:
        identity = (await session.execute(select(ExternalIdentity).where(
            ExternalIdentity.platform == "zalo",
            ExternalIdentity.external_user_id == str(payload["external_user_id"]),
            ExternalIdentity.revoked_at.is_(None),
        ))).scalar_one_or_none()
        if identity is None:
            raise PermissionError("Zalo identity da bi revoke hoac khong ton tai")
        user = await session.get(AppUser, identity.app_user_id)
        if user is None:
            raise PermissionError("App user khong ton tai")
        is_group = bool(payload.get("is_group"))
        course_id = None
        if is_group:
            binding = (await session.execute(select(ExternalChannelBinding).where(
                ExternalChannelBinding.platform == "zalo",
                ExternalChannelBinding.channel_id == str(payload["channel_id"]),
                ExternalChannelBinding.is_active.is_(True),
            ))).scalar_one_or_none()
            if binding is None:
                raise PermissionError("Zalo group chua bind course")
            course_id = binding.course_id
        result = await handle_chat(
            session, user_id=user.id, user_role=user.role, is_admin=user.role == "ADMIN",
            message=str(payload["text"]), course_id=course_id, is_group=is_group,
        )
    for chunk in format_zalo_reply(result.answer, result.citations, settings.public_web_url):
        await client.send_text(str(payload["external_user_id"]), chunk)
