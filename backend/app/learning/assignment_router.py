"""
Giao bài tập trắc nghiệm + chấm điểm tự động (Tác vụ #13).

QUYẾT ĐỊNH THIẾT KẾ (đã thảo luận và chốt cùng người dùng):

1. TRẮC NGHIỆM, không phải tự luận - chấm bằng cách SO ĐÁP ÁN, không
   gọi LLM chấm bài. Lý do: chính xác 100% và tức thì, trong khi LLM
   chấm vừa tốn tiền mỗi lượt vừa không nhất quán (cùng 1 bài có thể
   chấm khác nhau ở 2 lần khác nhau) - không chấp nhận được với thứ
   ảnh hưởng tới điểm số thật của sinh viên.

2. TÁI SỬ DỤNG kho câu hỏi đã có (quiz_question, sinh sẵn theo khái
   niệm ở Tác vụ #10) thay vì sinh riêng cho bài tập - không tốn thêm
   lượt gọi LLM nếu khái niệm đó đã từng có câu hỏi.

3. Nộp bài CŨNG cập nhật mastery (qua chính hàm apply_answer dùng cho
   quiz tự luyện) - nhất quán với nguyên tắc "mastery = năng lực đã
   được kiểm chứng qua bài kiểm tra", và bài tập giao chính là một
   dạng kiểm tra.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.db.models import (
    AppUser,
    Assignment,
    AssignmentQuestion,
    AssignmentSubmission,
    Concept,
    Course,
    Enrollment,
    QuizAttempt,
    QuizQuestion,
)
from app.db.session import get_db
from app.learning.assignment_schemas import (
    AnswerResult,
    AssignmentDetail,
    AssignmentPublic,
    AssignmentQuestionPublic,
    AssignmentResults,
    ConceptDifficulty,
    CreateAssignmentRequest,
    StudentResultSummary,
    SubmitAssignmentRequest,
    SubmitAssignmentResponse,
)
from app.learning.mastery import apply_answer, get_or_create_mastery
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter

router = APIRouter(prefix="/v1/assignments", tags=["assignments"])


async def _require_enrolled(session: AsyncSession, *, user_id: int, course_id: int) -> None:
    result = await session.execute(
        select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.course_id == course_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không thuộc lớp học này."
        )


async def _require_course_owner(session: AsyncSession, *, user: AppUser, course_id: int) -> Course:
    result = await session.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")
    if course.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không phải giáo viên phụ trách lớp này."
        )
    return course


@router.post("", response_model=AssignmentPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def create_assignment(
    request: Request,
    body: CreateAssignmentRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Giảng viên giao bài: chọn các khái niệm cần kiểm tra, hệ thống lấy
    câu hỏi tương ứng (sinh mới nếu khái niệm đó chưa có câu hỏi nào).
    """
    await _require_course_owner(session, user=user, course_id=body.course_id)

    # Chỉ nhận khái niệm THUỘC ĐÚNG lớp này - chặn việc giao bài chứa
    # câu hỏi của lớp khác (dù vô tình hay cố ý).
    concepts = (
        await session.execute(
            select(Concept).where(
                Concept.id.in_(body.concept_ids), Concept.course_id == body.course_id
            )
        )
    ).scalars().all()

    if len(concepts) != len(set(body.concept_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Có khái niệm không tồn tại hoặc không thuộc lớp này.",
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

    # Lấy câu hỏi cho từng khái niệm - dùng lại hàm đã có ở
    # app/learning/router.py để không lặp logic sinh/cache câu hỏi.
    from app.learning.router import _get_or_create_quiz_question

    for order, concept in enumerate(concepts):
        question = await _get_or_create_quiz_question(session, concept=concept, user_id=user.id)
        session.add(
            AssignmentQuestion(
                assignment_id=assignment.id, quiz_question_id=question.id, ord=order
            )
        )

    await session.commit()
    await session.refresh(assignment)

    return AssignmentPublic(
        id=assignment.id,
        course_id=assignment.course_id,
        title=assignment.title,
        description=assignment.description,
        due_at=assignment.due_at,
        question_count=len(concepts),
    )


@router.get("", response_model=list[AssignmentPublic])
async def list_assignments(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """Danh sách bài tập của lớp - kèm trạng thái nộp bài của chính người gọi."""
    await _require_enrolled(session, user_id=user.id, course_id=course_id)

    assignments = (
        await session.execute(
            select(Assignment).where(Assignment.course_id == course_id).order_by(Assignment.created_at.desc())
        )
    ).scalars().all()

    if not assignments:
        return []

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

    return [
        AssignmentPublic(
            id=a.id,
            course_id=a.course_id,
            title=a.title,
            description=a.description,
            due_at=a.due_at,
            question_count=counts.get(a.id, 0),
            my_score=submissions[a.id].score if a.id in submissions else None,
            my_total=submissions[a.id].total if a.id in submissions else None,
            submitted=a.id in submissions,
        )
        for a in assignments
    ]


@router.get("/{assignment_id}", response_model=AssignmentDetail)
async def get_assignment(
    assignment_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """Lấy đề bài để làm - KHÔNG kèm đáp án đúng (xem AssignmentQuestionPublic)."""
    assignment = (
        await session.execute(select(Assignment).where(Assignment.id == assignment_id))
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài tập.")

    await _require_enrolled(session, user_id=user.id, course_id=assignment.course_id)

    rows = (
        await session.execute(
            select(AssignmentQuestion, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == AssignmentQuestion.quiz_question_id)
            .where(AssignmentQuestion.assignment_id == assignment_id)
            .order_by(AssignmentQuestion.ord)
        )
    ).all()

    return AssignmentDetail(
        id=assignment.id,
        title=assignment.title,
        description=assignment.description,
        due_at=assignment.due_at,
        questions=[
            AssignmentQuestionPublic(
                quiz_question_id=q.id,
                ord=aq.ord,
                question=q.question,
                options=json.loads(q.options),
            )
            for aq, q in rows
        ],
    )


@router.post("/{assignment_id}/submit", response_model=SubmitAssignmentResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def submit_assignment(
    request: Request,
    assignment_id: int,
    body: SubmitAssignmentRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Nộp bài - chấm NGAY bằng cách so đáp án (không gọi LLM), đồng thời
    cập nhật mastery cho từng khái niệm liên quan.
    """
    assignment = (
        await session.execute(select(Assignment).where(Assignment.id == assignment_id))
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài tập.")

    await _require_enrolled(session, user_id=user.id, course_id=assignment.course_id)

    # Quá hạn thì không nhận bài - kiểm tra ở server, không tin vào việc
    # giao diện có ẩn nút nộp hay không.
    if assignment.due_at is not None and datetime.now(timezone.utc) > assignment.due_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Bài tập đã quá hạn nộp."
        )

    existing = (
        await session.execute(
            select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Bạn đã nộp bài này rồi."
        )

    rows = (
        await session.execute(
            select(AssignmentQuestion, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == AssignmentQuestion.quiz_question_id)
            .where(AssignmentQuestion.assignment_id == assignment_id)
        )
    ).all()
    questions_by_id = {q.id: q for _, q in rows}

    answers_by_id = {a.quiz_question_id: a.selected_index for a in body.answers}

    results: list[AnswerResult] = []
    score = 0
    for question_id, question in questions_by_id.items():
        selected = answers_by_id.get(question_id)
        # Câu không trả lời tính là SAI (selected=None) - không bỏ qua,
        # để tổng số câu luôn khớp số câu của đề.
        is_correct = selected is not None and selected == question.correct_index
        if is_correct:
            score += 1

        if selected is not None:
            session.add(
                QuizAttempt(
                    user_id=user.id,
                    quiz_question_id=question_id,
                    selected_index=selected,
                    is_correct=is_correct,
                )
            )
            mastery = await get_or_create_mastery(
                session, user_id=user.id, concept_id=question.concept_id
            )
            apply_answer(mastery, is_correct=is_correct)

        results.append(
            AnswerResult(
                quiz_question_id=question_id,
                is_correct=is_correct,
                correct_index=question.correct_index,
                explanation=question.explanation,
            )
        )

    total = len(questions_by_id)
    session.add(
        AssignmentSubmission(
            assignment_id=assignment_id, user_id=user.id, score=score, total=total
        )
    )

    try:
        await session.commit()
    except IntegrityError:
        # 2 lần nộp gần như đồng thời (double-click) - khoá chính CẶP
        # (assignment_id, user_id) chặn bản ghi thứ 2, cùng mẫu xử lý
        # TOCTOU đã dùng ở các endpoint khác.
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bạn đã nộp bài này rồi.")

    return SubmitAssignmentResponse(score=score, total=total, results=results)


@router.get("/{assignment_id}/results", response_model=AssignmentResults)
async def get_assignment_results(
    assignment_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Kết quả cả lớp - CHỈ giảng viên phụ trách xem được.

    Khác với thống kê hội thoại (ẩn danh hoàn toàn, xem
    app/instructor/router.py): điểm bài tập là kết quả học tập chính
    thức, giảng viên ĐƯỢC PHÉP xem theo từng sinh viên - đây là chức
    năng chấm bài bình thường, không phải theo dõi riêng tư.
    """
    assignment = (
        await session.execute(select(Assignment).where(Assignment.id == assignment_id))
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài tập.")

    await _require_course_owner(session, user=user, course_id=assignment.course_id)

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
            .where(
                Enrollment.course_id == assignment.course_id,
                Enrollment.role_in_course == "STUDENT",
            )
        )
    ).scalar_one()

    total_questions = (
        await session.execute(
            select(func.count())
            .select_from(AssignmentQuestion)
            .where(AssignmentQuestion.assignment_id == assignment_id)
        )
    ).scalar_one()

    # Khái niệm nào cả lớp làm sai nhiều nhất - chỉ tính các lượt trả
    # lời thuộc ĐÚNG các câu hỏi của bài tập này.
    question_ids = (
        await session.execute(
            select(AssignmentQuestion.quiz_question_id).where(
                AssignmentQuestion.assignment_id == assignment_id
            )
        )
    ).scalars().all()

    concept_stats: list[ConceptDifficulty] = []
    if question_ids:
        stats_rows = (
            await session.execute(
                select(
                    Concept.id,
                    Concept.name,
                    func.count(QuizAttempt.id),
                    func.sum(cast(QuizAttempt.is_correct, Integer)),
                )
                .join(QuizQuestion, QuizQuestion.concept_id == Concept.id)
                .join(QuizAttempt, QuizAttempt.quiz_question_id == QuizQuestion.id)
                .where(QuizQuestion.id.in_(question_ids))
                .group_by(Concept.id, Concept.name)
            )
        ).all()

        for concept_id, concept_name, total_count, correct_count in stats_rows:
            correct = int(correct_count or 0)
            concept_stats.append(
                ConceptDifficulty(
                    concept_id=concept_id,
                    concept_name=concept_name,
                    correct_count=correct,
                    total_count=total_count,
                    accuracy=(correct / total_count) if total_count else 0.0,
                )
            )
        concept_stats.sort(key=lambda c: c.accuracy)  # khó nhất (đúng ít nhất) lên đầu

    scores = [s.score for s, _ in submissions]

    return AssignmentResults(
        assignment_id=assignment_id,
        title=assignment.title,
        submitted_count=len(submissions),
        enrolled_count=enrolled_count,
        average_score=(sum(scores) / len(scores)) if scores else 0.0,
        total_questions=total_questions,
        students=[
            StudentResultSummary(
                user_id=s.user_id,
                full_name=u.full_name,
                score=s.score,
                total=s.total,
                submitted_at=s.submitted_at,
            )
            for s, u in submissions
        ],
        concept_difficulty=concept_stats,
    )
