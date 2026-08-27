"""
Endpoint chat chính thức - nối toàn bộ pipeline (Guardrail, Router,
Retrieval, sinh câu trả lời) qua app/academic_agent/agent.py.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic_agent.agent import _build_arguments_summary, handle_chat, handle_chat_stream
from app.academic_agent.schemas import ChatRequest, ChatResponse, CitationPublic, MessagePublic, PendingActionPublic
from app.academic_agent.tools import TOOL_LABELS_VI
from app.academic_agent.suggested_questions import get_suggested_questions
from app.academic_agent.summary import summarize_conversation
from app.auth.dependencies import get_current_user
from app.db.models import AppUser, Conversation, Message
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
        user_role=user.role,
        is_admin=user.role == "ADMIN",
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
        pending_action=result.pending_action,
        action_result=result.action_result,
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
            user_role=user.role,
            is_admin=user.role == "ADMIN",
            message=body.message,
            conversation_id=body.conversation_id,
            course_id=body.course_id,
            force_category=body.force_category,
            concept_id=body.concept_id,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{conversation_id}/suggested-questions")
async def get_suggestions(
    conversation_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Lấy danh sách câu hỏi gợi ý dựa trên context của cuộc trò chuyện.
    Backend phân tích conversation hiện tại để đưa ra 3-5 câu hỏi
    liên quan mà người dùng có thể nắm nhưũng hoặc tìm hiểu thêm.
    """
    suggestions = await get_suggested_questions(session, conversation_id, user.id)
    return suggestions


@router.get("/{conversation_id}/summary")
async def get_conversation_summary(
    conversation_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Tóm tắt cuộc trò chuyện - phân tích toàn bộ lịch sử để tạo
    summary, key points và covered concepts.
    """
    result = await summarize_conversation(session, conversation_id, user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện hoặc không có tin nhắn nào")
    return result


@router.get("/{conversation_id}/messages", response_model=list[MessagePublic])
async def get_conversation_messages(
    conversation_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Toàn bộ lịch sử tin nhắn của 1 cuộc hội thoại, sắp theo thời gian
    TĂNG DẦN (cũ -> mới, đúng thứ tự đọc tự nhiên trên UI) - dùng cho
    frontend "hydrate" lại ChatBubble sau khi F5/đăng nhập lại.

    KIỂM TRA QUYỀN SỞ HỮU: Conversation.user_id == user.id - copy đúng
    pattern đã dùng ở get_suggestions()/get_conversation_summary() phía
    trên trong cùng file. BẮT BUỘC phải có bước này: nếu bỏ qua, đổi
    conversation_id trên URL (path traversal đơn giản) sẽ lộ toàn bộ
    nội dung hội thoại của người dùng KHÁC - lỗ hổng bảo mật nghiêm
    trọng, không phải chi tiết vặt.
    """
    conv_result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conv_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cuộc trò chuyện này.",
        )

    messages_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = messages_result.scalars().all()

    # citations được lưu dạng CHUỖI JSON trên cột Message.citations (xem
    # docstring model Message trong db/models.py) - không phải bảng
    # riêng, nên chỉ cần json.loads() thay vì join thêm bảng nào khác.
    # Cùng format dict {chunk_id, document_id, page_number} đã dùng ở
    # ChatResponse (POST /v1/chat) - tái dùng thẳng CitationPublic, không
    # viết lại logic serialize citation.
    def _pending_action_public(m: Message) -> PendingActionPublic | None:
        # Chỉ tin nhắn assistant có pending_action mới cần "hydrate" lại -
        # xem docstring MessagePublic.pending_action. Import cục bộ helper
        # từ agent.py để KHÔNG lặp logic build arguments_summary.
        if not m.pending_action:
            return None
        try:
            parsed = json.loads(m.pending_action)
        except (json.JSONDecodeError, TypeError):
            return None
        tool_name = parsed.get("tool_name", "")
        arguments = parsed.get("arguments", {})

        return PendingActionPublic(
            tool_name=tool_name,
            tool_label_vi=TOOL_LABELS_VI.get(tool_name, tool_name),
            arguments_summary=_build_arguments_summary(tool_name, arguments),
        )

    return [
        MessagePublic(
            message_id=m.id,
            role=m.role,
            content=m.content,
            citations=[CitationPublic(**c) for c in json.loads(m.citations)] if m.citations else [],
            retrieval_similarity=m.retrieval_similarity,
            pending_action=_pending_action_public(m),
            created_at=m.created_at,
        )
        for m in messages
    ]
