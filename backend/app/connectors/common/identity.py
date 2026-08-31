import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.common.security import hash_link_code
from app.db.models import ExternalIdentity, ExternalIdentityLinkCode

LINK_CODE_TTL_MINUTES = 5


async def create_link_code(session: AsyncSession, *, user_id: int, platform: str) -> tuple[str, datetime]:
    code = secrets.token_urlsafe(18)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=LINK_CODE_TTL_MINUTES)
    session.add(ExternalIdentityLinkCode(
        app_user_id=user_id, platform=platform, code_hash=hash_link_code(code), expires_at=expires_at
    ))
    await session.flush()
    return code, expires_at


async def consume_link_code(
    session: AsyncSession, *, platform: str, external_user_id: str, code: str
) -> ExternalIdentity:
    now = datetime.now(timezone.utc)
    link = (
        await session.execute(
            select(ExternalIdentityLinkCode)
            .where(
                ExternalIdentityLinkCode.platform == platform,
                ExternalIdentityLinkCode.code_hash == hash_link_code(code),
                ExternalIdentityLinkCode.used_at.is_(None),
                ExternalIdentityLinkCode.expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ma lien ket khong hop le hoac da het han.")
    existing_external = (
        await session.execute(select(ExternalIdentity).where(
            ExternalIdentity.platform == platform,
            ExternalIdentity.external_user_id == external_user_id,
        ))
    ).scalar_one_or_none()
    existing_app = (
        await session.execute(select(ExternalIdentity).where(
            ExternalIdentity.platform == platform,
            ExternalIdentity.app_user_id == link.app_user_id,
        ))
    ).scalar_one_or_none()
    if existing_external and existing_external.app_user_id != link.app_user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Danh tinh ngoai da lien ket tai khoan khac.")
    if existing_app and existing_app.external_user_id != external_user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tai khoan da lien ket danh tinh khac tren nen tang nay.")
    identity = existing_external or existing_app
    if identity is None:
        identity = ExternalIdentity(platform=platform, external_user_id=external_user_id, app_user_id=link.app_user_id)
        session.add(identity)
    else:
        identity.revoked_at = None
        identity.verified_at = now
    link.used_at = now
    await session.flush()
    return identity
