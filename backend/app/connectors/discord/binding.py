from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import AppUser, Course, ExternalChannelBinding, ExternalIdentity
from app.db.session import AsyncSessionLocal


async def bind_discord_channel(*, external_user_id: str, channel_id: str, course_code: str) -> int:
    async with AsyncSessionLocal() as session:
        identity = (await session.execute(select(ExternalIdentity).where(
            ExternalIdentity.platform == "discord",
            ExternalIdentity.external_user_id == external_user_id,
            ExternalIdentity.revoked_at.is_(None),
        ))).scalar_one_or_none()
        if identity is None:
            raise PermissionError("Hay lien ket tai khoan Discord voi Nova tren web truoc.")
        user = await session.get(AppUser, identity.app_user_id)
        course = (await session.execute(select(Course).where(Course.code == course_code))).scalar_one_or_none()
        if course is None:
            raise LookupError("Khong tim thay ma lop.")
        if user is None or (user.role != "ADMIN" and course.owner_id != user.id):
            raise PermissionError("Chi giang vien so huu lop moi duoc bind kenh.")
        existing = (await session.execute(select(ExternalChannelBinding).where(
            ExternalChannelBinding.platform == "discord",
            ExternalChannelBinding.channel_id == channel_id,
        ))).scalar_one_or_none()
        if existing and existing.course_id != course.id:
            raise ValueError("Kenh da bind voi mot lop khac.")
        binding = existing or ExternalChannelBinding(
            platform="discord", channel_id=channel_id, course_id=course.id, created_by=user.id,
        )
        if existing is None:
            session.add(binding)
        binding.course_id = course.id
        binding.created_by = user.id
        binding.privacy_mode = "MENTION_ONLY"
        binding.is_active = True
        await session.commit()
        return course.id
