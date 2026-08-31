import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.connectors.common.identity import consume_link_code, create_link_code
from app.connectors.common.schemas import (
    ChannelBindRequest, ChannelBindingPublic, LinkCodePublic, LinkCodeRequest,
    EventAuditPublic, LinkIdentityRequest, MessageEnvelope, WebhookAccepted,
)
from app.connectors.common.security import verify_webhook_signature
from app.db.models import (
    AppUser, ConnectorOutbox, Course, ExternalChannelBinding, ExternalIdentity,
    ExternalMessageEvent,
)
from app.db.session import get_db

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])
PLATFORMS = {"mock", "discord", "zalo", "messenger"}


def _platform(value: str) -> str:
    if value not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Nen tang khong duoc ho tro.")
    return value


async def _require_course_owner(session: AsyncSession, user: AppUser, course_id: int) -> None:
    owner_id = (await session.execute(select(Course.owner_id).where(Course.id == course_id))).scalar_one_or_none()
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Khong tim thay lop hoc.")
    if user.role != "ADMIN" and owner_id != user.id:
        raise HTTPException(status_code=403, detail="Chi giang vien so huu lop moi duoc lien ket kenh.")


@router.post("/link-code", response_model=LinkCodePublic)
async def issue_link_code(body: LinkCodeRequest, session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    code, expires_at = await create_link_code(session, user_id=user.id, platform=body.platform)
    await session.commit()
    return LinkCodePublic(platform=body.platform, code=code, expires_at=expires_at)


@router.post("/{platform}/link")
async def link_external_identity(platform: str, body: LinkIdentityRequest, session: AsyncSession = Depends(get_db)):
    identity = await consume_link_code(
        session, platform=_platform(platform), external_user_id=body.external_user_id, code=body.code
    )
    await session.commit()
    return {"linked": True, "platform": platform, "external_user_id": identity.external_user_id}


@router.delete("/{platform}/identity/me")
async def revoke_identity(platform: str, session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    from datetime import datetime, timezone
    identity = (await session.execute(select(ExternalIdentity).where(
        ExternalIdentity.platform == _platform(platform), ExternalIdentity.app_user_id == user.id,
        ExternalIdentity.revoked_at.is_(None),
    ))).scalar_one_or_none()
    if identity:
        identity.revoked_at = datetime.now(timezone.utc)
        await session.commit()
    return {"revoked": identity is not None}


@router.post("/{platform}/channels/bind", response_model=ChannelBindingPublic)
async def bind_channel(platform: str, body: ChannelBindRequest, session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    platform = _platform(platform)
    await _require_course_owner(session, user, body.course_id)
    existing = (await session.execute(select(ExternalChannelBinding).where(
        ExternalChannelBinding.platform == platform, ExternalChannelBinding.channel_id == body.channel_id,
    ))).scalar_one_or_none()
    if existing and existing.course_id != body.course_id:
        raise HTTPException(status_code=409, detail="Kenh da duoc lien ket voi lop khac.")
    binding = existing or ExternalChannelBinding(
        platform=platform, channel_id=body.channel_id, course_id=body.course_id, created_by=user.id
    )
    if existing is None:
        session.add(binding)
    binding.privacy_mode = body.privacy_mode
    binding.is_active = True
    binding.created_by = user.id
    await session.commit()
    await session.refresh(binding)
    return ChannelBindingPublic.model_validate(binding, from_attributes=True)


@router.delete("/{platform}/channels/{channel_id}/bind")
async def unbind_channel(platform: str, channel_id: str, session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    binding = (await session.execute(select(ExternalChannelBinding).where(
        ExternalChannelBinding.platform == _platform(platform), ExternalChannelBinding.channel_id == channel_id,
        ExternalChannelBinding.is_active.is_(True),
    ))).scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=404, detail="Khong tim thay lien ket kenh.")
    await _require_course_owner(session, user, binding.course_id)
    binding.is_active = False
    await session.commit()
    return {"unbound": True}


@router.get("/bindings/me", response_model=list[ChannelBindingPublic])
async def list_my_bindings(session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    query = select(ExternalChannelBinding).where(ExternalChannelBinding.is_active.is_(True))
    if user.role != "ADMIN":
        query = query.join(Course, Course.id == ExternalChannelBinding.course_id).where(Course.owner_id == user.id)
    rows = (await session.execute(query.order_by(ExternalChannelBinding.created_at.desc()))).scalars()
    return [ChannelBindingPublic.model_validate(row, from_attributes=True) for row in rows]


@router.get("/events/audit", response_model=list[EventAuditPublic])
async def list_event_audit(session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Chi quan tri vien duoc xem audit connector.")
    rows = (await session.execute(
        select(ExternalMessageEvent).order_by(ExternalMessageEvent.created_at.desc()).limit(100)
    )).scalars()
    return [EventAuditPublic.model_validate(row, from_attributes=True) for row in rows]


@router.post("/{platform}/webhook", response_model=WebhookAccepted)
async def receive_webhook(
    platform: str, request: Request, session: AsyncSession = Depends(get_db),
    x_nova_timestamp: str = Header(default=""), x_nova_signature: str = Header(default=""),
):
    platform = _platform(platform)
    raw = await request.body()
    settings = get_settings()
    secret = settings.connector_webhook_secret or settings.jwt_secret
    if not verify_webhook_signature(
        secret=secret, timestamp=x_nova_timestamp, body=raw, signature=x_nova_signature
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook signature khong hop le.")
    try:
        envelope = MessageEnvelope.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Webhook payload khong hop le.") from exc

    existing = (await session.execute(select(ExternalMessageEvent).where(
        ExternalMessageEvent.platform == platform,
        ExternalMessageEvent.external_event_id == envelope.external_event_id,
    ))).scalar_one_or_none()
    if existing:
        return WebhookAccepted(accepted=True, duplicate=True, event_id=existing.id)

    identity = (await session.execute(select(ExternalIdentity.id).where(
        ExternalIdentity.platform == platform,
        ExternalIdentity.external_user_id == envelope.external_user_id,
        ExternalIdentity.revoked_at.is_(None),
    ))).scalar_one_or_none()
    if identity is None:
        raise HTTPException(status_code=403, detail="Danh tinh ngoai chua duoc lien ket.")
    if envelope.is_group:
        binding = (await session.execute(select(ExternalChannelBinding).where(
            ExternalChannelBinding.platform == platform,
            ExternalChannelBinding.channel_id == envelope.channel_id,
            ExternalChannelBinding.is_active.is_(True),
        ))).scalar_one_or_none()
        if binding is None:
            raise HTTPException(status_code=403, detail="Kenh chua duoc lien ket voi lop.")
        if binding.privacy_mode == "MENTION_ONLY" and not envelope.mentioned_nova:
            raise HTTPException(status_code=403, detail="Nova chi xu ly tin nhan duoc mention trong group.")

    statement = insert(ExternalMessageEvent).values(
        platform=platform, external_event_id=envelope.external_event_id,
        external_user_id=envelope.external_user_id, channel_id=envelope.channel_id,
        thread_id=envelope.thread_id, payload_hash=hashlib.sha256(raw).hexdigest(), status="RECEIVED",
    ).on_conflict_do_nothing(index_elements=["platform", "external_event_id"]).returning(ExternalMessageEvent.id)
    event_id = (await session.execute(statement)).scalar_one_or_none()
    if event_id is None:
        event_id = (await session.execute(select(ExternalMessageEvent.id).where(
            ExternalMessageEvent.platform == platform,
            ExternalMessageEvent.external_event_id == envelope.external_event_id,
        ))).scalar_one()
        await session.commit()
        return WebhookAccepted(accepted=True, duplicate=True, event_id=event_id)
    session.add(ConnectorOutbox(
        event_id=event_id,
        payload=json.dumps({"platform": platform, **envelope.model_dump(mode="json")}, ensure_ascii=False),
    ))
    await session.commit()
    return WebhookAccepted(accepted=True, duplicate=False, event_id=event_id)
