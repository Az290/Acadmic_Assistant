"""
Tool executor - thực thi THẬT các tool đã định nghĩa ở tools.py, sau
khi LLM (trong agent.py) đã chọn tool_name + arguments qua function-
calling.

RANH GIỚI AN TOÀN CỐT LÕI CỦA FILE NÀY (đọc trước khi sửa):
1. KHÔNG BAO GIỜ tin role/quyền mà LLM ngầm giả định khi chọn tool -
   tools.get_tools_for_role() chỉ là bộ lọc THUẬN TIỆN (giảm khả năng
   LLM tự gợi ý sai), KHÔNG PHẢI lớp bảo mật. Mọi tool ở đây tự kiểm
   tra lại RBAC (course owner/enrollment) y hệt các endpoint FastAPI
   gốc, KHÔNG rút gọn.
2. Đây KHÔNG PHẢI FastAPI endpoint - lỗi RBAC/validate/nghiệp vụ trả
   về qua ToolExecutionResult(success=False, ...), KHÔNG raise
   HTTPException (không có request/response cycle nào ở tầng này để
   bắt exception đó).
3. Dispatch bằng if/elif tường minh theo tool_name - CỐ Ý KHÔNG dùng
   eval/getattr động: dễ đọc, dễ audit hơn, và không có rủi ro gọi
   nhầm 1 hàm ngoài ý muốn nếu tool_name trùng tên 1 hàm nội bộ nào đó.
4. MỌI lượt gọi (thành công hay thất bại) đều ghi 1 dòng AgentActionLog
   - đây là audit trail đầy đủ theo đúng mục đích thiết kế của bảng đó
   (xem docstring AgentActionLog trong app/db/models.py).
5. KHÔNG tự ý session.commit() nếu logic gốc (router FastAPI tương ứng)
   không làm vậy ở đúng thời điểm đó - giữ nguyên transaction boundary
   đã có, tránh commit sớm làm lệch hành vi so với endpoint gốc.
"""

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic_agent.tools import TOOLS_REQUIRING_CONFIRMATION
from app.db.models import (
    AgentActionLog,
    Assignment,
    AssignmentQuestion,
    AssignmentSubmission,
    AppUser,
    Concept,
    Conversation,
    Course,
    Document,
    Enrollment,
    Message,
    QuizAttempt,
    QuizQuestion,
    StudentMastery,
)
from app.learning.assignment_schemas import CreateAssignmentRequest
from app.learning.learning_path import get_learning_path
from app.learning.mastery import get_or_create_mastery
from app.learning.mastery_overview import compute_weak_concepts
from app.learning.schemas import CreateConceptRequest
from app.courses.schemas import CreateCourseRequest, EnrollRequest
from app.documents.schemas import RejectDocumentRequest


@dataclass
class ToolExecutionResult:
    success: bool
    data: dict | None = None  # kết quả nếu thành công (dict JSON-serializable)
    error_message: str | None = None  # lý do thất bại, TIẾNG VIỆT, rõ ràng cho người dùng đọc


# ---------- Helper RBAC - copy ĐÚNG pattern đã có ở các router gốc ----------
# (courses/router.py, instructor/router.py, learning/assignment_router.py
# đều có 1 bản _require_course_owner gần giống nhau, KHÔNG import chéo -
# cùng nguyên tắc đã chốt: logic ngắn, trùng lặp rẻ hơn coupling nhiều
# router lại với nhau. Ở đây gộp lại 1 bản DÙNG CHUNG trong nội bộ file
# này vì tool_executor không phải router, không có lý do phải tách theo
# domain như 3 router kia.)


async def _get_course_or_none(session: AsyncSession, course_id: int) -> Course | None:
    result = await session.execute(select(Course).where(Course.id == course_id))
    return result.scalar_one_or_none()


def _is_course_owner(course: Course, user: AppUser) -> bool:
    return course.owner_id == user.id or user.role == "ADMIN"


async def _require_enrolled(session: AsyncSession, *, user_id: int, course_id: int) -> bool:
    result = await session.execute(
        select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.course_id == course_id)
    )
    return result.scalar_one_or_none() is not None


# ---------- Tool ĐỌC - GIẢNG VIÊN ----------


async def _tool_get_class_analytics(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    students = (
        await session.execute(
            select(AppUser.id, AppUser.full_name)
            .join(Enrollment, Enrollment.user_id == AppUser.id)
            .where(Enrollment.course_id == course_id, Enrollment.role_in_course == "STUDENT")
        )
    ).all()

    mastery_rows = (
        await session.execute(
            select(StudentMastery.user_id, StudentMastery.n_correct, StudentMastery.n_obs, Concept.name)
            .join(Concept, Concept.id == StudentMastery.concept_id)
            .where(Concept.course_id == course_id, StudentMastery.n_obs > 0)
        )
    ).all()

    per_student: dict[int, dict] = {}
    for uid, n_correct, n_obs, concept_name in mastery_rows:
        entry = per_student.setdefault(uid, {"correct": 0, "obs": 0, "weakest": None, "weakest_acc": 2.0})
        entry["correct"] += n_correct
        entry["obs"] += n_obs
        accuracy = n_correct / n_obs
        if accuracy < entry["weakest_acc"]:
            entry["weakest_acc"] = accuracy
            entry["weakest"] = concept_name

    needing_support = []
    mastery_values: list[float] = []
    for uid, full_name in students:
        entry = per_student.get(uid)
        if entry is None or entry["obs"] == 0:
            continue
        mastery = entry["correct"] / entry["obs"]
        mastery_values.append(mastery)
        if mastery < 0.4:
            needing_support.append(
                {"full_name": full_name, "mastery": round(mastery, 3), "weakest_concept": entry["weakest"]}
            )
    needing_support.sort(key=lambda s: s["mastery"])

    return ToolExecutionResult(
        success=True,
        data={
            "total_students": len(students),
            "students_with_data": len(mastery_values),
            "avg_mastery": round(sum(mastery_values) / len(mastery_values), 3) if mastery_values else None,
            "needing_support_count": len(needing_support),
            "students_needing_support": needing_support[:10],
        },
    )


async def _tool_get_course_roster(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    students = (
        await session.execute(
            select(AppUser.id, AppUser.full_name, AppUser.email)
            .join(Enrollment, Enrollment.user_id == AppUser.id)
            .where(Enrollment.course_id == course_id, Enrollment.role_in_course == "STUDENT")
            .order_by(Enrollment.joined_at)
        )
    ).all()

    return ToolExecutionResult(
        success=True,
        data={
            "course_code": course.code,
            "student_count": len(students),
            "students": [{"user_id": s.id, "full_name": s.full_name, "email": s.email} for s in students],
        },
    )


async def _tool_get_popular_concepts(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    from sqlalchemy import func

    rows = (
        await session.execute(
            select(
                Concept.name,
                func.count(Message.id),
                func.avg(Message.retrieval_similarity),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(Concept, Concept.id == Message.concept_id)
            .where(
                Conversation.course_id == course_id,
                Message.role == "assistant",
                Message.concept_id.is_not(None),
            )
            .group_by(Concept.id, Concept.name)
            .order_by(func.count(Message.id).desc())
            .limit(10)
        )
    ).all()

    return ToolExecutionResult(
        success=True,
        data={
            "concepts": [
                {
                    "name": name,
                    "question_count": count,
                    "avg_similarity": round(float(avg_sim), 3) if avg_sim is not None else None,
                }
                for name, count, avg_sim in rows
            ]
        },
    )


async def _tool_get_pending_documents(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    rows = (
        await session.execute(
            select(Document.id, Document.title, Document.created_at)
            .where(Document.course_id == course_id, Document.status == "PENDING_REVIEW")
            .order_by(Document.created_at)
        )
    ).all()

    return ToolExecutionResult(
        success=True,
        data={
            "pending_count": len(rows),
            "documents": [
                {"document_id": d_id, "title": title, "created_at": str(created_at)}
                for d_id, title, created_at in rows
            ],
        },
    )


async def _tool_get_assignment_results(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    assignment_id = args.get("assignment_id")
    assignment = (
        await session.execute(select(Assignment).where(Assignment.id == assignment_id))
    ).scalar_one_or_none()
    if assignment is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy bài tập này.")

    course = await _get_course_or_none(session, assignment.course_id)
    if course is None or not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp có bài tập này.")

    from sqlalchemy import func

    submissions = (
        await session.execute(
            select(AssignmentSubmission, AppUser)
            .join(AppUser, AppUser.id == AssignmentSubmission.user_id)
            .where(AssignmentSubmission.assignment_id == assignment_id)
            .order_by(AssignmentSubmission.score.desc())
        )
    ).all()

    enrolled_count = (
        await session.execute(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.course_id == assignment.course_id, Enrollment.role_in_course == "STUDENT")
        )
    ).scalar_one()

    scores = [s.score for s, _ in submissions]

    return ToolExecutionResult(
        success=True,
        data={
            "title": assignment.title,
            "submitted_count": len(submissions),
            "enrolled_count": enrolled_count,
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "students": [
                {"full_name": u.full_name, "score": s.score, "total": s.total} for s, u in submissions[:20]
            ],
        },
    )


async def _tool_get_costs(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    from app.instructor.pricing import estimate_cost_usd

    rows = (
        await session.execute(
            select(Message.token_usage)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.course_id == course_id,
                Message.role == "assistant",
                Message.token_usage.is_not(None),
            )
        )
    ).scalars().all()

    total_cost = 0.0
    for token_usage_json in rows:
        usage = json.loads(token_usage_json)
        generate = usage.get("generate", {})
        total_cost += estimate_cost_usd(generate.get("model", ""), generate.get("input", 0), generate.get("output", 0))

    n = len(rows)
    return ToolExecutionResult(
        success=True,
        data={
            "total_messages_measured": n,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_message_usd": round(total_cost / n, 6) if n else 0.0,
        },
    )


async def _tool_get_pipeline_timing(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

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
    for latency_json in rows:
        latency = json.loads(latency_json)
        for key in step_keys:
            if key in latency:
                values_by_step[key].append(latency[key])

    return ToolExecutionResult(
        success=True,
        data={
            "total_messages_measured": len(rows),
            "avg_ms_by_step": {
                key: round(sum(vals) / len(vals), 1) if vals else 0.0 for key, vals in values_by_step.items()
            },
        },
    )


# ---------- Tool ĐỌC - SINH VIÊN ----------


async def _tool_get_my_mastery(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    if not await _require_enrolled(session, user_id=user.id, course_id=course_id):
        return ToolExecutionResult(success=False, error_message="Bạn chưa thuộc lớp học này.")

    concepts = (
        await session.execute(select(Concept.id, Concept.name).where(Concept.course_id == course_id))
    ).all()

    mastery_rows = []
    for concept_id, concept_name in concepts:
        mastery = await get_or_create_mastery(session, user_id=user.id, concept_id=concept_id)
        mastery_rows.append(
            {
                "concept_name": concept_name,
                "n_obs": mastery.n_obs,
                "n_correct": mastery.n_correct,
                "mastered": mastery.mastered,
            }
        )
    await session.commit()  # get_or_create_mastery có thể tạo dòng mới - cùng hành vi endpoint gốc

    return ToolExecutionResult(success=True, data={"concepts": mastery_rows})


async def _tool_get_my_assignments(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    if not await _require_enrolled(session, user_id=user.id, course_id=course_id):
        return ToolExecutionResult(success=False, error_message="Bạn chưa thuộc lớp học này.")

    from sqlalchemy import func

    assignments = (
        await session.execute(
            select(Assignment).where(Assignment.course_id == course_id).order_by(Assignment.created_at.desc())
        )
    ).scalars().all()

    if not assignments:
        return ToolExecutionResult(success=True, data={"assignments": []})

    assignment_ids = [a.id for a in assignments]
    counts = dict(
        (
            await session.execute(
                select(AssignmentQuestion.assignment_id, func.count())
                .where(AssignmentQuestion.assignment_id.in_(assignment_ids))
                .group_by(AssignmentQuestion.assignment_id)
            )
        ).all()
    )
    submissions = {
        s.assignment_id: s
        for s in (
            await session.execute(
                select(AssignmentSubmission).where(
                    AssignmentSubmission.assignment_id.in_(assignment_ids),
                    AssignmentSubmission.user_id == user.id,
                )
            )
        ).scalars().all()
    }

    return ToolExecutionResult(
        success=True,
        data={
            "assignments": [
                {
                    "title": a.title,
                    "question_count": counts.get(a.id, 0),
                    "submitted": a.id in submissions,
                    "score": submissions[a.id].score if a.id in submissions else None,
                    "total": submissions[a.id].total if a.id in submissions else None,
                }
                for a in assignments
            ]
        },
    )


async def _tool_get_learning_path(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    try:
        result = await get_learning_path(session, course_id=course_id, user_id=user.id)
    except ValueError as e:
        return ToolExecutionResult(success=False, error_message=str(e))

    return ToolExecutionResult(
        success=True,
        data={
            "course_name": result.course_name,
            "concepts": [
                {"name": c.name, "status": c.status.value if hasattr(c.status, "value") else c.status, "mastery": c.mastery}
                for c in result.concepts
            ],
            "recommendations": [
                {"type": r.type, "concept_name": r.concept_name, "reason": r.reason} for r in result.recommendations
            ],
        },
    )


async def _tool_get_my_weakest_concept(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    weak_concepts = await compute_weak_concepts(session, user_id=user.id)
    candidates = [w for w in weak_concepts if w.accuracy < 0.5]
    if not candidates:
        return ToolExecutionResult(success=True, data={"has_weak_concept": False})

    weakest = candidates[0]
    return ToolExecutionResult(
        success=True,
        data={
            "has_weak_concept": True,
            "concept_name": weakest.concept_name,
            "accuracy": round(weakest.accuracy, 3),
            "n_obs": weakest.n_obs,
        },
    )


def _mistake_row_to_dict(question: QuizQuestion, attempt: QuizAttempt, concept_name: str) -> dict:
    """Gộp 1 QuizAttempt sai + QuizQuestion liên quan thành dict trả về
    cho LLM - dùng chung giữa get_my_recent_mistakes và explain_my_answer
    để tránh lặp logic parse options/lấy text đáp án."""
    options = json.loads(question.options)
    return {
        "quiz_question_id": question.id,
        "question": question.question,
        "options": options,
        "your_answer": options[attempt.selected_index] if 0 <= attempt.selected_index < len(options) else None,
        "correct_answer": options[question.correct_index] if 0 <= question.correct_index < len(options) else None,
        "is_correct": attempt.is_correct,
        "explanation": question.explanation,
        "concept_name": concept_name,
        "attempted_at": str(attempt.attempted_at),
    }


async def _tool_get_my_recent_mistakes(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    """
    RBAC: lọc CỨNG theo QuizAttempt.user_id == user.id - sinh viên
    KHÔNG BAO GIỜ xem được lịch sử làm bài của người khác qua tool này,
    bất kể course_id truyền vào là gì.
    """
    course_id = args.get("course_id")
    limit = args.get("limit") or 5
    limit = max(1, min(int(limit), 20))  # chặn limit bất thường (0, âm, quá lớn)

    query = (
        select(QuizAttempt, QuizQuestion, Concept.name)
        .join(QuizQuestion, QuizQuestion.id == QuizAttempt.quiz_question_id)
        .join(Concept, Concept.id == QuizQuestion.concept_id)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.is_correct.is_(False))
        .order_by(QuizAttempt.attempted_at.desc())
        .limit(limit)
    )
    if course_id is not None:
        query = query.where(Concept.course_id == course_id)

    rows = (await session.execute(query)).all()

    return ToolExecutionResult(
        success=True,
        data={
            "mistakes": [
                _mistake_row_to_dict(question, attempt, concept_name)
                for attempt, question, concept_name in rows
            ]
        },
    )


async def _tool_explain_my_answer(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    """
    RBAC bắt buộc: CHỈ trả dữ liệu nếu CHÍNH sinh viên này đã từng làm
    ĐÚNG câu hỏi đó (có dòng QuizAttempt khớp user_id + quiz_question_id).
    Không có dòng attempt khớp -> từ chối, KHÔNG lộ nội dung/đáp án đúng
    của câu hỏi - tránh lỗ hổng dò đáp án các câu CHƯA làm bằng cách
    đoán quiz_question_id tuần tự.
    """
    quiz_question_id = args.get("quiz_question_id")

    attempt = (
        await session.execute(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user.id, QuizAttempt.quiz_question_id == quiz_question_id)
            .order_by(QuizAttempt.attempted_at.desc())
        )
    ).scalars().first()
    if attempt is None:
        return ToolExecutionResult(
            success=False,
            error_message="Bạn chưa từng làm câu hỏi này, nên mình không thể hiển thị đáp án.",
        )

    question = (
        await session.execute(select(QuizQuestion).where(QuizQuestion.id == quiz_question_id))
    ).scalar_one_or_none()
    if question is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy câu hỏi này.")

    concept_name = (
        await session.execute(select(Concept.name).where(Concept.id == question.concept_id))
    ).scalar_one_or_none()

    return ToolExecutionResult(success=True, data=_mistake_row_to_dict(question, attempt, concept_name or ""))


# ---------- Tool GHI - GIẢNG VIÊN (đã qua xác nhận khi tới đây) ----------


async def _tool_create_concept(
    session: AsyncSession, args: dict, user: AppUser
) -> ToolExecutionResult:
    try:
        body = CreateConceptRequest(**args)
    except Exception as e:
        return ToolExecutionResult(success=False, error_message=f"Tham số không hợp lệ: {e}")

    course = await _get_course_or_none(session, body.course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    import asyncio

    from app.ingestion.embedder import embed_texts

    embedding = await asyncio.to_thread(embed_texts, [body.name])

    concept = Concept(
        course_id=body.course_id,
        name=body.name,
        complexity=body.complexity,
        created_by=user.id,
        embedding=embedding[0],
        prerequisites=json.dumps(body.prerequisites) if body.prerequisites else None,
    )
    session.add(concept)
    await session.commit()
    await session.refresh(concept)

    return ToolExecutionResult(
        success=True,
        data={"concept_id": concept.id, "name": concept.name, "complexity": concept.complexity},
    )


async def _tool_create_assignment(
    session: AsyncSession, args: dict, user: AppUser
) -> ToolExecutionResult:
    try:
        body = CreateAssignmentRequest(**args)
    except Exception as e:
        return ToolExecutionResult(success=False, error_message=f"Tham số không hợp lệ: {e}")

    course = await _get_course_or_none(session, body.course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    concepts = (
        await session.execute(
            select(Concept).where(Concept.id.in_(body.concept_ids), Concept.course_id == body.course_id)
        )
    ).scalars().all()
    if len(concepts) != len(set(body.concept_ids)):
        return ToolExecutionResult(
            success=False, error_message="Có khái niệm không tồn tại hoặc không thuộc lớp này."
        )

    assignment = Assignment(
        course_id=body.course_id,
        title=body.title,
        description=body.description,
        due_at=body.due_at,
        created_by=user.id,
    )
    session.add(assignment)
    await session.flush()

    # Tái dùng ĐÚNG hàm cache-first đã có ở learning/router.py, không
    # viết lại logic sinh/cache câu hỏi - cùng cách assignment_router.py
    # gốc đang làm (import cục bộ để tránh vòng lặp import ở module cấp
    # cao, xem chú thích trong assignment_router.py::create_assignment).
    from app.learning.router import _get_or_create_quiz_question

    for order, concept in enumerate(concepts):
        question = await _get_or_create_quiz_question(session, concept=concept, user_id=user.id)
        session.add(AssignmentQuestion(assignment_id=assignment.id, quiz_question_id=question.id, ord=order))

    await session.commit()
    await session.refresh(assignment)

    return ToolExecutionResult(
        success=True,
        data={"assignment_id": assignment.id, "title": assignment.title, "question_count": len(concepts)},
    )


async def _tool_approve_document(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    document_id = args.get("document_id")
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy tài liệu này.")

    if document.course_id is None:
        return ToolExecutionResult(
            success=False,
            error_message="Tài liệu đóng góp chưa được phân lớp. Hãy duyệt trên trang Duyệt tài liệu và chọn lớp phù hợp.",
        )

    course = await _get_course_or_none(session, document.course_id)
    if course is None or not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp có tài liệu này.")

    if document.status != "PENDING_REVIEW":
        return ToolExecutionResult(
            success=False, error_message=f"Tài liệu đang ở trạng thái '{document.status}', không thể duyệt."
        )

    document.status = "APPROVED"
    await session.commit()

    return ToolExecutionResult(success=True, data={"document_id": document.id, "title": document.title, "status": "APPROVED"})


async def _tool_reject_document(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    try:
        body = RejectDocumentRequest(reason=args.get("reason"))
    except Exception as e:
        return ToolExecutionResult(success=False, error_message=f"Tham số không hợp lệ: {e}")

    document_id = args.get("document_id")
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy tài liệu này.")

    if document.course_id is not None:
        course = await _get_course_or_none(session, document.course_id)
        if course is None or not _is_course_owner(course, user):
            return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp có tài liệu này.")

    if document.status != "PENDING_REVIEW":
        return ToolExecutionResult(
            success=False, error_message=f"Tài liệu đang ở trạng thái '{document.status}', không thể từ chối."
        )

    document.status = "REJECTED"
    if body.reason:
        document.rejection_reason = body.reason
    await session.commit()

    return ToolExecutionResult(success=True, data={"document_id": document.id, "title": document.title, "status": "REJECTED"})


async def _tool_remove_student_from_course(
    session: AsyncSession, args: dict, user: AppUser
) -> ToolExecutionResult:
    course_id = args.get("course_id")
    student_user_id = args.get("student_user_id")

    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    enrollment = (
        await session.execute(
            select(Enrollment).where(
                Enrollment.course_id == course_id,
                Enrollment.user_id == student_user_id,
                Enrollment.role_in_course == "STUDENT",
            )
        )
    ).scalar_one_or_none()
    if enrollment is None:
        return ToolExecutionResult(success=False, error_message="Sinh viên này không có trong lớp.")

    await session.delete(enrollment)
    await session.commit()

    return ToolExecutionResult(success=True, data={"course_id": course_id, "student_user_id": student_user_id})


async def _tool_enroll_student(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    course_id = args.get("course_id")
    try:
        body = EnrollRequest(student_email=args.get("student_email"))
    except Exception as e:
        return ToolExecutionResult(success=False, error_message=f"Email không hợp lệ: {e}")

    course = await _get_course_or_none(session, course_id)
    if course is None:
        return ToolExecutionResult(success=False, error_message="Không tìm thấy lớp học này.")
    if not _is_course_owner(course, user):
        return ToolExecutionResult(success=False, error_message="Bạn không phải giáo viên phụ trách lớp này.")

    student = (
        await session.execute(select(AppUser).where(AppUser.email == body.student_email))
    ).scalar_one_or_none()
    if student is None:
        return ToolExecutionResult(
            success=False,
            error_message="Không tìm thấy học sinh với email này - học sinh cần đăng ký tài khoản trước.",
        )

    already = (
        await session.execute(
            select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == course_id)
        )
    ).scalar_one_or_none()
    if already is not None:
        return ToolExecutionResult(success=False, error_message="Học sinh này đã ở trong lớp.")

    session.add(Enrollment(user_id=student.id, course_id=course_id, role_in_course="STUDENT"))
    await session.commit()

    return ToolExecutionResult(success=True, data={"course_id": course_id, "student_email": body.student_email})


async def _tool_create_course(session: AsyncSession, args: dict, user: AppUser) -> ToolExecutionResult:
    try:
        body = CreateCourseRequest(**args)
    except Exception as e:
        return ToolExecutionResult(success=False, error_message=f"Tham số không hợp lệ: {e}")

    if user.role not in ("INSTRUCTOR", "ADMIN"):
        return ToolExecutionResult(success=False, error_message="Chỉ giảng viên mới được tạo lớp học.")

    existing = (await session.execute(select(Course).where(Course.code == body.code))).scalar_one_or_none()
    if existing is not None:
        return ToolExecutionResult(success=False, error_message="Mã lớp này đã tồn tại.")

    course = Course(code=body.code, name=body.name, owner_id=user.id)
    session.add(course)
    await session.flush()
    session.add(Enrollment(user_id=user.id, course_id=course.id, role_in_course="INSTRUCTOR"))
    await session.commit()
    await session.refresh(course)

    return ToolExecutionResult(success=True, data={"course_id": course.id, "code": course.code, "name": course.name})


_DISPATCH_READ = {
    "get_class_analytics": _tool_get_class_analytics,
    "get_course_roster": _tool_get_course_roster,
    "get_popular_concepts": _tool_get_popular_concepts,
    "get_pending_documents": _tool_get_pending_documents,
    "get_assignment_results": _tool_get_assignment_results,
    "get_costs": _tool_get_costs,
    "get_pipeline_timing": _tool_get_pipeline_timing,
    "get_my_mastery": _tool_get_my_mastery,
    "get_my_assignments": _tool_get_my_assignments,
    "get_learning_path": _tool_get_learning_path,
    "get_my_weakest_concept": _tool_get_my_weakest_concept,
    "get_my_recent_mistakes": _tool_get_my_recent_mistakes,
    "explain_my_answer": _tool_explain_my_answer,
}

_DISPATCH_WRITE = {
    "create_concept": _tool_create_concept,
    "create_assignment": _tool_create_assignment,
    "approve_document": _tool_approve_document,
    "reject_document": _tool_reject_document,
    "remove_student_from_course": _tool_remove_student_from_course,
    "enroll_student": _tool_enroll_student,
    "create_course": _tool_create_course,
}


def _summarize_result(tool_name: str, result: ToolExecutionResult) -> str:
    """Tóm tắt ngắn TIẾNG VIỆT cho AgentActionLog.result_summary."""
    if result.success:
        return f"Thực thi thành công tool '{tool_name}'."
    return f"Thất bại: {result.error_message}"


async def execute_tool(
    session: AsyncSession, *, tool_name: str, arguments: dict, user: AppUser, conversation_id: int
) -> ToolExecutionResult:
    """
    Điểm vào DUY NHẤT để thực thi 1 tool - agent.py chỉ cần gọi hàm này,
    không cần biết tool nào thuộc nhóm đọc/ghi hay dispatch ra sao.

    Ghi AgentActionLog CHO MỌI tool GHI (cả thành công lẫn thất bại) -
    tool ĐỌC KHÔNG ghi log (không thay đổi dữ liệu, không cần audit
    trail loại này - AgentActionLog dành riêng cho hành động THAY ĐỔI
    dữ liệu, xem docstring model).
    """
    handler = _DISPATCH_READ.get(tool_name) or _DISPATCH_WRITE.get(tool_name)
    if handler is None:
        return ToolExecutionResult(success=False, error_message=f"Không nhận diện được hành động '{tool_name}'.")

    result = await handler(session, arguments, user)

    if tool_name in TOOLS_REQUIRING_CONFIRMATION:
        session.add(
            AgentActionLog(
                user_id=user.id,
                conversation_id=conversation_id,
                tool_name=tool_name,
                arguments=json.dumps(arguments, ensure_ascii=False),
                success=result.success,
                result_summary=_summarize_result(tool_name, result),
            )
        )
        await session.commit()

    return result
