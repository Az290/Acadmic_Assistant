from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserLearningPreference
from app.personalization.schemas import DEFAULT_PREFERENCE, PreferencePatch, PreferencePublic


async def get_preference(session: AsyncSession, user_id: int) -> PreferencePublic:
    row = (
        await session.execute(
            select(UserLearningPreference).where(UserLearningPreference.user_id == user_id)
        )
    ).scalar_one_or_none()
    return PreferencePublic.model_validate(row) if row else DEFAULT_PREFERENCE.model_copy()


async def update_preference(
    session: AsyncSession, user_id: int, patch: PreferencePatch
) -> PreferencePublic:
    row = (
        await session.execute(
            select(UserLearningPreference).where(UserLearningPreference.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserLearningPreference(user_id=user_id)
        session.add(row)
    for field, value in patch.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    row.source = "explicit"
    await session.flush()
    await session.refresh(row)
    return PreferencePublic.model_validate(row)


async def delete_preference(session: AsyncSession, user_id: int) -> None:
    row = (
        await session.execute(
            select(UserLearningPreference).where(UserLearningPreference.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
