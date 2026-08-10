"""
Dashboard giảng viên (Tác vụ #9, phần thống kê) - thống kê TỔNG HỢP
theo LỚP, KHÔNG cá nhân hoá theo từng sinh viên.

NGUYÊN TẮC QUYỀN RIÊNG TƯ (đã chốt từ đầu dự án): giảng viên KHÔNG
được đọc nội dung hội thoại cá nhân của sinh viên - chỉ xem được số
liệu TỔNG HỢP (bao nhiêu câu thuộc category nào, tỷ lệ không tìm thấy
tài liệu, bao nhiêu lần bị Guardrail chặn) - không endpoint nào ở đây
trả về nội dung `message.content` gắn với 1 user_id cụ thể.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.db.models import AppUser, Conversation, Course, Enrollment, Message, SecurityLog
from app.db.session import get_db
from app.instructor.schemas import (
    CategoryCount,
    InstructorAnalytics,
    InsufficientContextRate,
    SecurityAlertSummary,
)

router = APIRouter(prefix="/v1/instructor", tags=["instructor"])


async def _require_course_owner(session: AsyncSession, *, user: AppUser, course_id: int) -> Course:
    result = await session.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")

    if course.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không phải giáo viên phụ trách lớp này.",
        )
    return course


@router.get("/analytics", response_model=InstructorAnalytics)
async def get_analytics(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    3 widget theo đúng đặc tả gốc Phần 7.3:
    1. category_breakdown - câu hỏi phổ biến theo loại (Top khái niệm
       bị hỏi nhiều - ở mức đơn giản hơn "khái niệm cụ thể", đây là
       theo CATEGORY vì dự án chưa có bảng concept gắn với mọi câu hỏi).
    2. insufficient_context - "Điểm mù tài liệu": tỷ lệ câu hỏi CẦN
       retrieval nhưng không tìm thấy chunk liên quan (citations rỗng)
       - giá trị sư phạm LỚN NHẤT theo đặc tả, chỉ ra tài liệu còn thiếu.
    3. security_alerts - Cảnh báo liêm chính (thống kê, KHÔNG định
       danh) - đếm SecurityLog của các user thuộc lớp này.
    """
    await _require_course_owner(session, user=user, course_id=course_id)

    # Lấy toàn bộ Message role='assistant' thuộc các Conversation của course này
    base_query = (
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.course_id == course_id, Message.role == "assistant")
    )

    total_result = await session.execute(select(func.count()).select_from(base_query.subquery()))
    total_messages = total_result.scalar_one()

    category_result = await session.execute(
        select(Message.category, func.count())
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.course_id == course_id, Message.role == "assistant", Message.category.is_not(None))
        .group_by(Message.category)
    )
    category_breakdown = [CategoryCount(category=cat, count=cnt) for cat, cnt in category_result.all()]

    # "Điểm mù tài liệu": needs_retrieval=True nhưng citations rỗng/NULL
    # (Hybrid Search không tìm thấy chunk liên quan nào để trả lời).
    rag_total_result = await session.execute(
        select(func.count())
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.course_id == course_id,
            Message.role == "assistant",
            Message.needs_retrieval.is_(True),
        )
    )
    total_rag_questions = rag_total_result.scalar_one()

    insufficient_result = await session.execute(
        select(func.count())
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.course_id == course_id,
            Message.role == "assistant",
            Message.needs_retrieval.is_(True),
            (Message.citations.is_(None)) | (Message.citations == "[]"),
        )
    )
    insufficient_count = insufficient_result.scalar_one()

    insufficient_context = InsufficientContextRate(
        total_rag_questions=total_rag_questions,
        insufficient_count=insufficient_count,
        rate=(insufficient_count / total_rag_questions) if total_rag_questions > 0 else 0.0,
    )

    # SecurityLog không có course_id trực tiếp - suy ra qua Enrollment
    # (user nào thuộc course này). GIỚI HẠN CÓ CHỦ Ý: nếu 1 user thuộc
    # NHIỀU course, lần bị chặn của họ sẽ tính vào TẤT CẢ course họ
    # thuộc về (không biết chính xác họ đang hỏi trong ngữ cảnh course
    # nào khi bị chặn) - chấp nhận được vì đây là số liệu CẢNH BÁO XU
    # HƯỚNG, không phải bằng chứng pháp lý cần chính xác tuyệt đối.
    security_result = await session.execute(
        select(SecurityLog.blocked_by, func.count())
        .join(Enrollment, Enrollment.user_id == SecurityLog.user_id)
        .where(Enrollment.course_id == course_id)
        .group_by(SecurityLog.blocked_by)
    )
    security_alerts = [SecurityAlertSummary(blocked_by=b, count=c) for b, c in security_result.all()]

    return InstructorAnalytics(
        course_id=course_id,
        total_messages=total_messages,
        category_breakdown=category_breakdown,
        insufficient_context=insufficient_context,
        security_alerts=security_alerts,
    )
