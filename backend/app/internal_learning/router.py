from fastapi import APIRouter, Depends

from app.auth.dependencies import require_role
from app.db.models import AppUser
from app.internal_learning.service import load_modules


router = APIRouter(prefix="/v1/internal-learning", tags=["internal-learning"])


@router.get("/modules")
async def list_internal_learning_modules(
    _owner: AppUser = Depends(require_role("OWNER")),
) -> list[dict]:
    """Nội dung không nằm trong frontend bundle và chỉ OWNER được tải."""
    return load_modules()

