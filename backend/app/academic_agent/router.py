"""
Endpoint chat chính thức - nối toàn bộ pipeline (Guardrail, Router,
Retrieval, sinh câu trả lời) qua app/academic_agent/agent.py.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic_agent.agent import handle_chat
from app.academic_agent.schemas import ChatRequest, ChatResponse
from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.db.session import get_db
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def chat(
    request: Request,
    body: ChatRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Gửi 1 câu hỏi tới Academic Agent - nếu conversation_id không được
    truyền, hệ thống tự tạo 1 phiên hội thoại mới và trả về id của nó
    để dùng cho các lượt hỏi tiếp theo trong cùng phiên.
    """
    result = await handle_chat(
        session,
        user_id=user.id,
        message=body.message,
        conversation_id=body.conversation_id,
        course_id=body.course_id,
    )
    return ChatResponse(
        conversation_id=result.conversation_id,
        answer=result.answer,
        category=result.category,
        citations=result.citations,
        blocked=result.blocked,
    )
