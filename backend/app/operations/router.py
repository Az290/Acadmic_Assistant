from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.db.session import get_db
from app.operations.service import get_operations_snapshot, retention_preview, run_retention, snapshot_dict

router = APIRouter(prefix="/v1/operations", tags=["operations"])


def _require_admin(user: AppUser) -> None:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Chi quan tri vien duoc xem van hanh he thong.")


@router.get("/status")
async def operations_status(session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    _require_admin(user)
    return snapshot_dict(await get_operations_snapshot(session))


@router.get("/retention/preview")
async def preview_retention(session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    _require_admin(user)
    return await retention_preview(session)


@router.post("/retention/run")
async def execute_retention(session: AsyncSession = Depends(get_db), user: AppUser = Depends(get_current_user)):
    _require_admin(user)
    return await run_retention(session)
