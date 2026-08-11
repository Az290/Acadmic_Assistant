"""
Hồ sơ cá nhân - thống kê sử dụng của CHÍNH người dùng đang đăng nhập.

Khác hẳn app/instructor/ (Dashboard giảng viên xem số liệu TỔNG HỢP của
cả lớp) - đây là trang cá nhân, mỗi người chỉ xem được dữ liệu của
chính mình (user_id lấy từ JWT, không nhận tham số nào từ client).
"""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AppUser, Conversation, Message, QuizAttempt, StudentMastery
from app.db.session import get_db
from app.profile.history_schemas import ConversationHistoryItem
from app.profile.schemas import ProfileStats

router = APIRouter(prefix="/v1/profile", tags=["profile"])

# Lịch sử tối đa trả về 1 lần - tránh query/trả JSON quá lớn cho user
# dùng lâu năm đã tích luỹ hàng trăm cuộc hội thoại. Chưa làm phân
# trang (MVP) - đủ dùng để xem lại các câu hỏi GẦN ĐÂY, là nhu cầu
# chính của trang này.
HISTORY_LIMIT = 50


@router.get("/stats", response_model=ProfileStats)
async def get_profile_stats(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # role='user' - đếm CÂU HỎI đã đặt, không tính message trả lời của AI
    # (khác conversation.user_id: đó là chủ sở hữu phiên chat, còn ở đây
    # cần lọc đúng role để không đếm gấp đôi mỗi lượt hỏi-đáp).
    total_questions = (
        await session.execute(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user.id, Message.role == "user")
        )
    ).scalar_one()

    questions_this_week = (
        await session.execute(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user.id,
                Message.role == "user",
                Message.created_at >= week_ago,
            )
        )
    ).scalar_one()

    quizzes_taken = (
        await session.execute(select(func.count(QuizAttempt.id)).where(QuizAttempt.user_id == user.id))
    ).scalar_one()

    # SUM(n_correct)/SUM(n_obs) - KHÔNG phải AVG(n_correct/n_obs) từng
    # dòng: trung bình cộng các tỷ lệ sẽ cho 1 concept mới học (2 câu,
    # đúng 1) trọng số ngang với 1 concept đã luyện nhiều (20 câu, đúng
    # 18) - sai bản chất, "mastery trung bình" phải phản ánh đúng tỷ lệ
    # đúng THẬT trên tổng số câu đã làm.
    totals = (
        await session.execute(
            select(func.sum(StudentMastery.n_correct), func.sum(StudentMastery.n_obs)).where(
                StudentMastery.user_id == user.id
            )
        )
    ).one()
    sum_correct, sum_obs = totals
    avg_mastery = (sum_correct / sum_obs) if sum_obs else None

    return ProfileStats(
        total_questions=total_questions,
        questions_this_week=questions_this_week,
        quizzes_taken=quizzes_taken,
        avg_mastery=round(avg_mastery, 3) if avg_mastery is not None else None,
    )


@router.get("/history", response_model=list[ConversationHistoryItem])
async def get_conversation_history(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Lịch sử hỏi-đáp của CHÍNH người dùng, MỚI NHẤT TRƯỚC.

    CHỈ hiện các lượt hỏi-đáp đã THỰC SỰ ĐƯỢC LƯU (category thuộc
    RAG_QUESTION/SOCRATIC_REQUEST/CHITCHAT/OFF_TOPIC) - câu hỏi bị
    Guardrail chặn KHÔNG được lưu vào Message ở giai đoạn hiện tại
    (xem app/academic_agent/agent.py, cả input và output block đều
    chỉ trả response tạm cho client, không persist) nên không thể và
    không nên xuất hiện ở đây.

    Ghép cặp (câu hỏi, câu trả lời) bằng cách duyệt tuần tự message
    trong TỪNG conversation theo thời gian - schema hiện tại KHÔNG có
    liên kết trực tiếp giữa message user và message assistant tương
    ứng (không có parent_message_id), chỉ có chung conversation_id.
    """
    # Lấy đủ message của user (không giới hạn ở tầng SQL vì cần ghép
    # cặp trước rồi mới cắt HISTORY_LIMIT theo ĐƠN VỊ CẶP HỎI-ĐÁP, không
    # phải theo đơn vị message) - số lượng message của 1 user vẫn ở quy
    # mô nhỏ (hàng trăm, không phải hàng triệu) nên chấp nhận được.
    rows = (
        await session.execute(
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user.id)
            .order_by(Message.conversation_id, Message.id)
        )
    ).scalars().all()

    # Đếm tổng số lượt Socratic trong TỪNG conversation trước - dùng để
    # hiện "Socratic (N lượt)" đúng như prototype (N = tổng số lượt
    # trao đổi Socratic trong CẢ phiên, không phải chỉ tới thời điểm
    # câu này).
    socratic_count_per_conversation: dict[int, int] = {}
    for m in rows:
        if m.role == "assistant" and m.category == "SOCRATIC_REQUEST":
            socratic_count_per_conversation[m.conversation_id] = (
                socratic_count_per_conversation.get(m.conversation_id, 0) + 1
            )

    items: list[ConversationHistoryItem] = []
    pending_question: str | None = None
    for m in rows:
        if m.role == "user":
            pending_question = m.content
            continue

        # role == "assistant" - ghép với câu hỏi liền trước trong CÙNG
        # conversation (đã order_by conversation_id, id nên không lẫn
        # câu hỏi từ conversation khác).
        if pending_question is None or m.category is None:
            continue

        source_count: int | None
        if m.category == "RAG_QUESTION":
            source_count = len(json.loads(m.citations)) if m.citations else 0
        elif m.category == "SOCRATIC_REQUEST":
            source_count = socratic_count_per_conversation.get(m.conversation_id, 1)
        else:  # CHITCHAT, OFF_TOPIC - không có khái niệm "nguồn"
            source_count = None

        items.append(
            ConversationHistoryItem(
                question=pending_question,
                category=m.category,
                created_at=m.created_at,
                source_count=source_count,
            )
        )
        pending_question = None

    items.sort(key=lambda it: it.created_at, reverse=True)
    return items[:HISTORY_LIMIT]
