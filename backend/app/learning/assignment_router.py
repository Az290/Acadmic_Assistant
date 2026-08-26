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
    GeneratedQuizQuestionPublic,
    GenerateQuestionsRequest,
    StudentResultSummary,
    SubmitAssignmentRequest,
    SubmitAssignmentResponse,
    UpdateQuizQuestionRequest,
)
from app.learning.mastery import apply_answer, get_or_create_mastery
from app.learning.quiz_generator import QuizGenerationError, generate_quiz_question
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter

router = APIRouter(prefix="/v1/assignments", tags=["assignments"])

# Router RIÊNG cho /v1/quiz-questions/{id} (PATCH sửa câu hỏi nháp) - path
# không nằm dưới /v1/assignments nên KHÔNG dùng chung `router` ở trên (prefix
# lệch), nhưng đăng ký cùng app.main như các router khác (xem app/main.py).
quiz_questions_router = APIRouter(prefix="/v1/quiz-questions", tags=["assignments"])


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


@router.post("/generate-questions", response_model=list[GeneratedQuizQuestionPublic])
@limiter.limit(DEFAULT_RATE_LIMIT)
async def generate_questions(
    request: Request,
    body: GenerateQuestionsRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Sinh NHÁP câu hỏi cho giảng viên xem/sửa/duyệt trước khi giao bài.

    KHÁC với _get_or_create_quiz_question (dùng ở luồng sinh viên tự
    luyện /v1/learn/quiz): ở đây LUÔN sinh câu MỚI, KHÔNG cache/tái sử
    dụng câu cũ - giảng viên bấm "Sinh câu hỏi" là muốn 1 bộ đề mới để
    duyệt, không phải lấy lại câu đã có sẵn trong kho.

    Câu hỏi sinh ra ĐƯỢC LƯU vào DB ngay (có id thật) để giảng viên có
    thể PATCH sửa hoặc chọn giao qua POST /v1/assignments - nhưng CHƯA
    gắn với assignment_question nào nên không xuất hiện với sinh viên
    cho tới khi thực sự được giao.
    """
    await _require_course_owner(session, user=user, course_id=body.course_id)

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

    generated_questions: list[GeneratedQuizQuestionPublic] = []
    for concept in concepts:
        for _ in range(body.num_questions_per_concept):
            try:
                generated = await generate_quiz_question(
                    session, concept_name=concept.name, user_id=user.id
                )
            except QuizGenerationError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                )

            question = QuizQuestion(
                concept_id=concept.id,
                question=generated["question"],
                options=json.dumps(generated["options"], ensure_ascii=False),
                correct_index=generated["correct_index"],
                explanation=generated["explanation"],
            )
            session.add(question)
            await session.flush()

            generated_questions.append(
                GeneratedQuizQuestionPublic(
                    id=question.id,
                    concept_id=concept.id,
                    concept_name=concept.name,
                    question=question.question,
                    options=json.loads(question.options),
                    correct_index=question.correct_index,
                    explanation=question.explanation,
                )
            )

    await session.commit()
    return generated_questions


@router.post("", response_model=AssignmentPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def create_assignment(
    request: Request,
    body: CreateAssignmentRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Giảng viên giao bài. Có 2 luồng:

    1. MỚI (khuyến nghị): body.quiz_question_ids có giá trị - đây là
       các câu đã được giảng viên xem/sửa/duyệt qua bước
       POST .../generate-questions. Dùng ĐÚNG các câu này, theo ĐÚNG
       thứ tự đã truyền lên - không tự sinh gì thêm.

    2. CŨ (tương thích ngược): quiz_question_ids rỗng/None - hệ thống
       tự lấy/sinh 1 câu hỏi CACHE cho mỗi concept_ids như hành vi gốc.
       Giữ nguyên để không phá bất kỳ nơi nào khác đang gọi endpoint
       này theo kiểu cũ.
    """
    await _require_course_owner(session, user=user, course_id=body.course_id)

    assignment = Assignment(
        course_id=body.course_id,
        title=body.title,
        description=body.description,
        due_at=body.due_at,
        created_by=user.id,
    )
    session.add(assignment)
    await session.flush()

    if body.quiz_question_ids:
        # Luồng MỚI: câu hỏi giảng viên đã duyệt. Xác thực từng câu
        # THẬT SỰ thuộc 1 concept của ĐÚNG course này - chặn việc giao
        # nhầm/cố ý câu hỏi của lớp khác qua endpoint này.
        questions = (
            await session.execute(
                select(QuizQuestion)
                .join(Concept, Concept.id == QuizQuestion.concept_id)
                .where(
                    QuizQuestion.id.in_(body.quiz_question_ids),
                    Concept.course_id == body.course_id,
                )
            )
        ).scalars().all()
        questions_by_id = {q.id: q for q in questions}

        if len(questions_by_id) != len(set(body.quiz_question_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Có câu hỏi không tồn tại hoặc không thuộc lớp này.",
            )

        for order, qid in enumerate(body.quiz_question_ids):
            session.add(
                AssignmentQuestion(assignment_id=assignment.id, quiz_question_id=qid, ord=order)
            )
        question_count = len(body.quiz_question_ids)
    else:
        if not body.concept_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phải cung cấp concept_ids hoặc quiz_question_ids.",
            )

        # Chỉ nhận khái niệm THUỘC ĐÚNG lớp này - chặn việc giao bài
        # chứa câu hỏi của lớp khác (dù vô tình hay cố ý).
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
        question_count = len(concepts)

    await session.commit()
    await session.refresh(assignment)

    return AssignmentPublic(
        id=assignment.id,
        course_id=assignment.course_id,
        title=assignment.title,
        description=assignment.description,
        due_at=assignment.due_at,
        question_count=question_count,
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


@quiz_questions_router.patch("/{question_id}", response_model=GeneratedQuizQuestionPublic)
async def update_quiz_question(
    question_id: int,
    body: UpdateQuizQuestionRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Sửa 1 câu hỏi nháp trước khi giao bài (VIỆC 2 - giảng viên xem/sửa/duyệt).

    Chặn quyền qua ĐÚNG concept -> course -> owner_id của câu hỏi, KHÔNG
    nhận course_id từ body (tránh giả mạo course_id để bypass kiểm tra
    quyền sở hữu) - luôn tra ngược từ chính question_id.
    """
    question = (
        await session.execute(select(QuizQuestion).where(QuizQuestion.id == question_id))
    ).scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy câu hỏi này.")

    concept = (
        await session.execute(select(Concept).where(Concept.id == question.concept_id))
    ).scalar_one()  # concept_id là FK bắt buộc - luôn tồn tại nếu question tồn tại

    await _require_course_owner(session, user=user, course_id=concept.course_id)

    question.question = body.question
    question.options = json.dumps(body.options, ensure_ascii=False)
    question.correct_index = body.correct_index
    question.explanation = body.explanation

    await session.commit()
    await session.refresh(question)

    return GeneratedQuizQuestionPublic(
        id=question.id,
        concept_id=question.concept_id,
        concept_name=concept.name,
        question=question.question,
        options=json.loads(question.options),
        correct_index=question.correct_index,
        explanation=question.explanation,
    )
