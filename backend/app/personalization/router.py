from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.db.session import get_db
from app.personalization.schemas import MemoryPublic, PreferencePatch, PreferencePublic
from app.personalization.service import delete_preference, get_preference, update_preference
from app.personalization.memory_service import delete_user_memories, list_user_memories

router = APIRouter(prefix="/v1/nova/preferences", tags=["nova-personalization"])
memory_router = APIRouter(prefix="/v1/nova/memory", tags=["nova-personalization"])


@router.get("/me", response_model=PreferencePublic)
async def read_my_preferences(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    return await get_preference(session, user.id)


@router.patch("/me", response_model=PreferencePublic)
async def patch_my_preferences(
    body: PreferencePatch,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    result = await update_preference(session, user.id, body)
    await session.commit()
    return result


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def remove_my_preferences(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    await delete_preference(session, user.id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@memory_router.get("/me", response_model=list[MemoryPublic])
async def read_my_memories(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    return await list_user_memories(session, user.id)


@memory_router.delete("/me")
async def remove_my_memories(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    deleted = await delete_user_memories(session, user.id)
    await session.commit()
    return {"deleted": deleted}
