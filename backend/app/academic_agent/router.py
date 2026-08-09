"""
Endpoint chat chính thức - nối toàn bộ pipeline (Guardrail, Router,
Retrieval, sinh câu trả lời) qua app/academic_agent/agent.py.
"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic_agent.agent import handle_chat, handle_chat_stream
from app.academic_agent.schemas import ChatRequest, ChatResponse
from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.db.session import AsyncSessionLocal, get_db
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


@router.post("/stream")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def chat_stream(
    request: Request,
    body: ChatRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Biến thể STREAMING của /v1/chat - dùng Server-Sent Events (SSE) để
    hiển thị câu trả lời NGAY KHI model sinh ra, thay vì đợi toàn bộ
    xong mới trả về. Đánh đổi đã thảo luận rõ: Guardrail output chạy
    Ở NỀN (không chặn hiển thị) - xem
    app/academic_agent/agent.py::_run_output_guardrail_in_background.

    Định dạng mỗi dòng SSE: "data: {JSON}\\n\\n" - client (EventSource
    hoặc fetch + ReadableStream) tự parse theo chuẩn này.
    """

    async def event_generator():
        async for event in handle_chat_stream(
            session,
            AsyncSessionLocal,
            user_id=user.id,
            message=body.message,
            conversation_id=body.conversation_id,
            course_id=body.course_id,
            force_category=body.force_category,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
