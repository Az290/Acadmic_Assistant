"""
Dashboard giảng viên (Tác vụ #9, phần thống kê) - thống kê TỔNG HỢP
theo LỚP, KHÔNG cá nhân hoá theo từng sinh viên.

RANH GIỚI QUYỀN RIÊNG TƯ (cập nhật khi thêm /class-analytics):

ĐƯỢC PHÉP - dữ liệu SƯ PHẠM gắn với danh tính sinh viên: tên, mastery,
khái niệm đang yếu, số câu đã hỏi. Chỉ có ở /class-analytics, phục vụ
mục đích duy nhất là giúp giảng viên biết ai cần hỗ trợ.

KHÔNG BAO GIỜ - nội dung riêng tư: `message.content` gắn với 1 user_id
cụ thể, lịch sử hội thoại, câu trả lời AI đã sinh cho từng cá nhân.
Không endpoint nào trong file này trả về những dữ liệu đó, kể cả khi
giảng viên là chủ sở hữu lớp.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.db.models import (
    AppUser,
    Concept,
    Conversation,
    Course,
    Document,
    Enrollment,
    Message,
    MessageFeedback,
    SecurityLog,
    StudentMastery,
)
from app.db.session import get_db
from app.documents.schemas import DocumentPublic, PendingDocumentPublic, RejectDocumentRequest
from app.instructor.pricing import estimate_cost_usd
from app.instructor.schemas import (
    CategoryCount,
    CostSummary,
    PipelineStepTiming,
    PipelineTiming,
    ConceptGap,
    InstructorAnalytics,
    ClassAnalytics,
    InsufficientContextRate,
    MasteryDistributionBucket,
    PopularConcept,
    SecurityAlertSummary,
    StudentNeedingSupport,
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

    # GAP ANALYSIS: nhóm câu hỏi theo CHỦ ĐỀ (khái niệm), đếm riêng số
    # câu không tìm được tài liệu. Đây là bước cụ thể hoá của
    # insufficient_context ở trên - thay vì chỉ biết "33% câu hỏi không
    # có tài liệu", giảng viên biết ĐÍCH DANH chủ đề nào đang thiếu.
    is_unanswered = (Message.citations.is_(None)) | (Message.citations == "[]")
    gap_rows = (
        await session.execute(
            select(
                Message.concept_id,
                Concept.name,
                func.count(),
                func.sum(case((is_unanswered, 1), else_=0)),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .outerjoin(Concept, Concept.id == Message.concept_id)
            .where(
                Conversation.course_id == course_id,
                Message.role == "assistant",
                Message.needs_retrieval.is_(True),
            )
            .group_by(Message.concept_id, Concept.name)
        )
    ).all()

    concept_gaps = [
        ConceptGap(
            concept_id=cid,
            # concept_id NULL = câu hỏi không khớp khái niệm nào giảng
            # viên đã tạo. Vẫn hiển thị (gộp thành 1 dòng) vì đây cũng
            # là tín hiệu đáng chú ý: có thể lớp thiếu hẳn khái niệm đó.
            concept_name=name or "(Chưa phân loại chủ đề)",
            total_questions=total,
            unanswered_questions=int(unanswered or 0),
            gap_rate=(int(unanswered or 0) / total) if total else 0.0,
        )
        for cid, name, total, unanswered in gap_rows
    ]
    concept_gaps.sort(key=lambda g: (g.gap_rate, g.unanswered_questions), reverse=True)

    return InstructorAnalytics(
        course_id=course_id,
        total_messages=total_messages,
        category_breakdown=category_breakdown,
        insufficient_context=insufficient_context,
        security_alerts=security_alerts,
        concept_gaps=concept_gaps,
    )


# ---------- HITL: duyệt tài liệu (Tác vụ #13) ----------
#
# Tài liệu vừa upload có status='PENDING_REVIEW' (xem
# app/ingestion/pipeline.py) - KHÔNG khả dụng cho Hybrid Search cho tới
# khi giảng viên duyệt ở đây. curator_notes (nếu có) là cảnh báo TỰ
# ĐỘNG từ Curator Agent (app/curator/) - chỉ mang tính THAM KHẢO, giảng
# viên vẫn là người quyết định cuối cùng.


async def _require_document_owner(session: AsyncSession, *, user: AppUser, document_id: int) -> Document:
    result = await session.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu này.")

    await _require_course_owner(session, user=user, course_id=document.course_id)
    return document


@router.get("/documents/pending", response_model=list[PendingDocumentPublic])
async def list_pending_documents(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Hàng chờ duyệt - tài liệu đã ingest xong nhưng chưa công khai cho
    sinh viên, kèm thông tin AI đã đóng góp (giảng viên hay sinh viên).
    """
    await _require_course_owner(session, user=user, course_id=course_id)

    rows = (
        await session.execute(
            select(Document, AppUser)
            .join(AppUser, AppUser.id == Document.uploaded_by)
            .where(Document.course_id == course_id, Document.status == "PENDING_REVIEW")
            .order_by(Document.created_at)
        )
    ).all()

    return [
        PendingDocumentPublic(
            id=d.id,
            course_id=d.course_id,
            title=d.title,
            status=d.status,
            license_status=d.license_status,
            content_hash=d.content_hash,
            superseded_by_id=d.superseded_by_id,
            image_count=d.image_count,
            curator_notes=d.curator_notes,
            uploader_name=u.full_name,
            uploader_role=u.role,
        )
        for d, u in rows
    ]


@router.post("/documents/{document_id}/approve", response_model=DocumentPublic)
async def approve_document(
    document_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Duyệt - từ đây tài liệu MỚI khả dụng cho Hybrid Search (đúng nguyên
    tắc chặn ở tầng dữ liệu: chunk.document_id phải trỏ tới document có
    status='APPROVED', xem app/retrieval/hybrid_search.py).
    """
    document = await _require_document_owner(session, user=user, document_id=document_id)

    if document.status != "PENDING_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tài liệu đang ở trạng thái '{document.status}', không thể duyệt.",
        )

    document.status = "APPROVED"
    await session.commit()
    await session.refresh(document)
    return document


@router.post("/documents/{document_id}/reject", response_model=DocumentPublic)
async def reject_document(
    document_id: int,
    body: RejectDocumentRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Từ chối - tài liệu VẪN nằm trong database (không xoá, cùng lý do
    đã áp dụng cho document versioning: giữ lại để truy vết, không phá
    citation cũ nếu lỡ đã có ai trích dẫn trước khi bị từ chối) nhưng
    VĨNH VIỄN không xuất hiện trong kết quả tìm kiếm (status khác
    'APPROVED').
    """
    document = await _require_document_owner(session, user=user, document_id=document_id)

    if document.status != "PENDING_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tài liệu đang ở trạng thái '{document.status}', không thể từ chối.",
        )

    document.status = "REJECTED"
    if body.reason:
        document.rejection_reason = body.reason
    await session.commit()
    await session.refresh(document)
    return document


# ---------- Cost Dashboard + Pipeline Visualization ----------
#
# Cả 2 endpoint đọc từ Message.token_usage/latency_ms - CHỈ có ở
# message tạo SAU KHI tính năng đo lường này được thêm vào (xem
# app/academic_agent/agent.py). Message cũ (trước đó) có 2 cột này là
# NULL - bị bỏ qua tự động khi lọc is_not(None), không tính vào số
# liệu (không coi NULL là 0, tránh làm sai lệch trung bình).

DAYS_PER_MONTH = 30


@router.get("/costs", response_model=CostSummary)
async def get_cost_summary(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    await _require_course_owner(session, user=user, course_id=course_id)

    rows = (
        await session.execute(
            select(Message.token_usage, Message.created_at)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.course_id == course_id,
                Message.role == "assistant",
                Message.token_usage.is_not(None),
            )
        )
    ).all()

    enrolled_students = (
        await session.execute(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.course_id == course_id, Enrollment.role_in_course == "STUDENT")
        )
    ).scalar_one()

    total_input = 0
    total_output = 0
    total_cost = 0.0
    oldest_at = None
    newest_at = None

    for token_usage_json, created_at in rows:
        usage = json.loads(token_usage_json)
        generate = usage.get("generate", {})
        model = generate.get("model", "")
        input_tokens = generate.get("input", 0)
        output_tokens = generate.get("output", 0)
        total_input += input_tokens
        total_output += output_tokens
        total_cost += estimate_cost_usd(model, input_tokens, output_tokens)
        if oldest_at is None or created_at < oldest_at:
            oldest_at = created_at
        if newest_at is None or created_at > newest_at:
            newest_at = created_at

    n = len(rows)
    avg_cost = total_cost / n if n else 0.0

    # Dự báo: chi phí/câu x số câu/sinh viên/ngày ĐO ĐƯỢC x giả định
    # 100 sinh viên x 30 ngày - ước lượng thô (không tính mùa thi hay
    # biến động thực tế), chỉ để có con số tham khảo. Nếu chưa có sinh
    # viên nào trong lớp (enrolled_students=0), không chia được cho 0
    # -> trả về 0 thay vì lỗi.
    span_days = max((newest_at - oldest_at).days, 1) if oldest_at and newest_at else 1
    messages_per_student_per_day = (n / span_days / enrolled_students) if enrolled_students else 0.0
    projected = avg_cost * messages_per_student_per_day * 100 * DAYS_PER_MONTH

    return CostSummary(
        total_messages_measured=n,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost_usd=round(total_cost, 6),
        avg_cost_per_message_usd=round(avg_cost, 6),
        projected_monthly_usd_per_100_students=round(projected, 2),
    )


@router.get("/pipeline", response_model=PipelineTiming)
async def get_pipeline_timing(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Thời gian trung bình + p95 của từng bước xử lý - trả lời câu hỏi
    "bước nào đang làm chậm trải nghiệm người dùng" bằng SỐ LIỆU THẬT
    thay vì đo thủ công từng lần (như đã làm nhiều lần trước đây).
    """
    await _require_course_owner(session, user=user, course_id=course_id)

    rows = (
        await session.execute(
            select(Message.latency_ms)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.course_id == course_id,
                Message.role == "assistant",
                Message.latency_ms.is_not(None),
            )
        )
    ).scalars().all()

    step_keys = ["guardrail_router_ms", "retrieval_ms", "generate_ms"]
    values_by_step: dict[str, list[int]] = {k: [] for k in step_keys}
    totals: list[int] = []

    for latency_json in rows:
        latency = json.loads(latency_json)
        for key in step_keys:
            if key in latency:
                values_by_step[key].append(latency[key])
        if "total_ms" in latency:
            totals.append(latency["total_ms"])

    def _p95(values: list[int]) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = min(int(len(sorted_values) * 0.95), len(sorted_values) - 1)
        return float(sorted_values[index])

    steps = [
        PipelineStepTiming(
            step=key,
            avg_ms=round(sum(vals) / len(vals), 1) if vals else 0.0,
            p95_ms=_p95(vals),
        )
        for key, vals in values_by_step.items()
    ]

    return PipelineTiming(
        total_messages_measured=len(rows),
        steps=steps,
        avg_total_ms=round(sum(totals) / len(totals), 1) if totals else 0.0,
    )


# ---------- Câu hỏi phổ biến ----------
#
# NGƯỠNG MẪU TỐI THIỂU - lý do tồn tại: nếu cảnh báo ngay từ 1 câu hỏi
# đầu tiên có điểm thấp, giảng viên sẽ nhận hàng loạt báo động sai từ
# những chủ đề chỉ mới có 1-2 lượt hỏi ngẫu nhiên. Cảnh báo mất giá trị
# khi nó kêu quá thường xuyên.
MIN_QUESTIONS_FOR_ALERT = 3
MIN_FEEDBACK_FOR_RATE = 3

# Dưới ngưỡng này coi là hệ thống không tìm được tài liệu đủ khớp. Cao
# hơn MIN_RELEVANCE_SIMILARITY (0.30 - ngưỡng CHẶN, dưới đó trả rỗng
# hẳn): ở đây đang xét vùng "tìm được gì đó nhưng chưa thật sự khớp".
LOW_SIMILARITY_THRESHOLD = 0.5

# Dưới 60% phiếu tích cực = đa số sinh viên thấy câu trả lời chưa giúp được họ.
LOW_POSITIVE_RATE_THRESHOLD = 0.6


@router.get("/popular-concepts", response_model=list[PopularConcept])
async def get_popular_concepts(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Các khái niệm được hỏi nhiều nhất trong lớp, kèm 2 tín hiệu chất
    lượng: độ khớp tài liệu (máy đo) và tỷ lệ đánh giá tích cực (người
    đánh giá).

    KHÔNG trả về nội dung câu hỏi cụ thể của bất kỳ sinh viên nào - chỉ
    số liệu gom nhóm theo khái niệm, giữ đúng ranh giới riêng tư đã áp
    dụng cho toàn bộ Dashboard giảng viên.
    """
    await _require_course_owner(session, user=user, course_id=course_id)

    rows = (
        await session.execute(
            select(
                Message.concept_id,
                Concept.name,
                func.count(Message.id).label("question_count"),
                func.avg(Message.retrieval_similarity).label("avg_similarity"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(Concept, Concept.id == Message.concept_id)
            .where(
                Conversation.course_id == course_id,
                Message.role == "assistant",
                Message.concept_id.is_not(None),
            )
            .group_by(Message.concept_id, Concept.name)
            .order_by(func.count(Message.id).desc())
        )
    ).all()

    # Đếm phiếu đánh giá theo khái niệm - truy vấn RIÊNG thay vì JOIN
    # chung ở trên: 1 câu trả lời có thể có nhiều phiếu, JOIN thẳng sẽ
    # nhân bản dòng và làm sai chính question_count.
    feedback_rows = (
        await session.execute(
            select(
                Message.concept_id,
                func.count(MessageFeedback.message_id).label("feedback_count"),
                func.sum(case((MessageFeedback.is_positive.is_(True), 1), else_=0)).label("positive_count"),
            )
            .join(Message, Message.id == MessageFeedback.message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.course_id == course_id, Message.concept_id.is_not(None))
            .group_by(Message.concept_id)
        )
    ).all()
    feedback_by_concept = {
        concept_id: (int(feedback_count), int(positive_count or 0))
        for concept_id, feedback_count, positive_count in feedback_rows
    }

    result: list[PopularConcept] = []
    for concept_id, concept_name, question_count, avg_similarity in rows:
        feedback_count, positive_count = feedback_by_concept.get(concept_id, (0, 0))

        # Chưa đủ phiếu -> None ("chưa đủ dữ liệu"), KHÔNG phải 0.0
        # ("đã có phiếu và toàn bộ đều tiêu cực") - 2 tình huống hoàn
        # toàn khác nhau, hiển thị lẫn lộn sẽ khiến giảng viên kết luận
        # sai về chất lượng.
        positive_rate = (
            positive_count / feedback_count if feedback_count >= MIN_FEEDBACK_FOR_RATE else None
        )
        avg_sim = float(avg_similarity) if avg_similarity is not None else None

        needs_attention = (
            question_count >= MIN_QUESTIONS_FOR_ALERT
            and feedback_count >= MIN_FEEDBACK_FOR_RATE
            and avg_sim is not None
            and avg_sim < LOW_SIMILARITY_THRESHOLD
            and positive_rate is not None
            and positive_rate < LOW_POSITIVE_RATE_THRESHOLD
        )

        result.append(
            PopularConcept(
                concept_id=concept_id,
                concept_name=concept_name,
                question_count=question_count,
                avg_retrieval_similarity=round(avg_sim, 3) if avg_sim is not None else None,
                feedback_count=feedback_count,
                positive_rate=round(positive_rate, 3) if positive_rate is not None else None,
                needs_attention=needs_attention,
            )
        )

    return result


# ---------- Phân tích lớp ----------

# Dưới ngưỡng này coi là cần hỗ trợ - CHỈ áp dụng cho sinh viên ĐÃ có
# dữ liệu (n_obs > 0). Sinh viên chưa làm quiz nào không phải "yếu",
# họ chỉ là "chưa bắt đầu" - 2 tình huống cần 2 cách xử lý khác nhau.
NEEDS_SUPPORT_MASTERY_THRESHOLD = 0.4

# 5 khoảng phân bố, khớp đúng biểu đồ trong thiết kế giao diện.
_DISTRIBUTION_BUCKETS = [(0.0, 0.2, "0-20%"), (0.2, 0.4, "20-40%"), (0.4, 0.6, "40-60%"), (0.6, 0.8, "60-80%"), (0.8, 1.01, "80-100%")]


@router.get("/class-analytics", response_model=ClassAnalytics)
async def get_class_analytics(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Tình hình học tập của TỪNG sinh viên trong lớp - ai đang cần hỗ trợ.

    ĐÂY LÀ ENDPOINT DUY NHẤT trong app/instructor/ trả về dữ liệu gắn
    với danh tính sinh viên cụ thể, và chỉ giới hạn ở dữ liệu SƯ PHẠM
    (tên, mastery, khái niệm yếu, số câu đã hỏi). Xem docstring
    StudentNeedingSupport trong schemas.py về quyết định chính sách này.

    KHÔNG trả về: nội dung câu hỏi, câu trả lời, hay bất kỳ đoạn hội
    thoại nào của sinh viên.
    """
    await _require_course_owner(session, user=user, course_id=course_id)

    students = (
        await session.execute(
            select(AppUser.id, AppUser.full_name)
            .join(Enrollment, Enrollment.user_id == AppUser.id)
            .where(Enrollment.course_id == course_id, Enrollment.role_in_course == "STUDENT")
        )
    ).all()

    # Mastery theo từng sinh viên, CHỈ tính trên concept thuộc lớp này -
    # sinh viên có thể học nhiều lớp, không được trộn tiến độ lớp khác vào.
    mastery_rows = (
        await session.execute(
            select(StudentMastery.user_id, StudentMastery.n_correct, StudentMastery.n_obs, Concept.name)
            .join(Concept, Concept.id == StudentMastery.concept_id)
            .where(Concept.course_id == course_id, StudentMastery.n_obs > 0)
        )
    ).all()

    # Số câu đã hỏi trong lớp này theo từng sinh viên (chỉ đếm, không đọc nội dung).
    question_rows = (
        await session.execute(
            select(Conversation.user_id, func.count(Message.id))
            .join(Message, Message.conversation_id == Conversation.id)
            .where(Conversation.course_id == course_id, Message.role == "user")
            .group_by(Conversation.user_id)
        )
    ).all()
    questions_by_user = {user_id: count for user_id, count in question_rows}

    # Gom theo sinh viên: tổng đúng/tổng làm + tìm concept yếu nhất
    per_student: dict[int, dict] = {}
    for user_id, n_correct, n_obs, concept_name in mastery_rows:
        entry = per_student.setdefault(user_id, {"correct": 0, "obs": 0, "weakest": None, "weakest_acc": 2.0})
        entry["correct"] += n_correct
        entry["obs"] += n_obs
        accuracy = n_correct / n_obs
        if accuracy < entry["weakest_acc"]:
            entry["weakest_acc"] = accuracy
            entry["weakest"] = concept_name

    bucket_counts = {label: 0 for _, _, label in _DISTRIBUTION_BUCKETS}
    needing_support: list[StudentNeedingSupport] = []
    mastery_values: list[float] = []

    for user_id, full_name in students:
        entry = per_student.get(user_id)
        if entry is None or entry["obs"] == 0:
            continue  # chưa có dữ liệu - đếm riêng bên dưới, không vào phân bố

        # SUM(correct)/SUM(obs) - cùng công thức đã dùng ở /v1/profile/stats
        # và /v1/learn/mastery/overview, để mọi nơi trong hệ thống nói
        # cùng một con số cho cùng một sinh viên.
        mastery = entry["correct"] / entry["obs"]
        mastery_values.append(mastery)

        for low, high, label in _DISTRIBUTION_BUCKETS:
            if low <= mastery < high:
                bucket_counts[label] += 1
                break

        if mastery < NEEDS_SUPPORT_MASTERY_THRESHOLD:
            needing_support.append(
                StudentNeedingSupport(
                    user_id=user_id,
                    full_name=full_name,
                    mastery=round(mastery, 3),
                    weakest_concept_name=entry["weakest"],
                    question_count=questions_by_user.get(user_id, 0),
                )
            )

    needing_support.sort(key=lambda s: s.mastery)

    return ClassAnalytics(
        course_id=course_id,
        total_students=len(students),
        students_with_data=len(mastery_values),
        students_without_data=len(students) - len(mastery_values),
        avg_mastery=round(sum(mastery_values) / len(mastery_values), 3) if mastery_values else None,
        needing_support_count=len(needing_support),
        distribution=[
            MasteryDistributionBucket(label=label, student_count=bucket_counts[label])
            for _, _, label in _DISTRIBUTION_BUCKETS
        ],
        students_needing_support=needing_support,
    )
