"""
Learning Assistant (Tác vụ #10) - quiz thích ứng đơn giản + heuristic
mastery tracking. TÁCH RIÊNG khỏi chế độ Socratic trong ChatBubble
(app/academic_agent/) ở giai đoạn MVP này - 2 tính năng độc lập, chưa
kết nối (Socratic prompt CHƯA đọc mastery để tự điều chỉnh độ khó).
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.db.models import AppUser, Concept, Course, Enrollment, QuizAttempt, QuizQuestion, StudentMastery
from app.db.session import get_db
from app.ingestion.embedder import embed_texts
from app.learning.mastery import apply_answer, get_or_create_mastery
from app.learning.mastery_overview import (
    MASTERY_HIGH_THRESHOLD,
    MASTERY_LOW_THRESHOLD,
    compute_weak_concepts,
)
from app.learning.learning_path import get_learning_path
from app.learning.quiz_generator import (
    QuizGenerationError,
    generate_quiz_question,
    generate_quiz_questions_batch,
)
from app.learning.schemas import (
    AnswerResponse,
    ConceptProgressPublic,
    ConceptPublic,
    CourseMasteryPublic,
    CreateConceptRequest,
    LearningPathResponsePublic,
    RecommendationPublic,
    MasteryOverview,
    MasteryPublic,
    QuizAnswerResult,
    QuizQuestionPublic,
    QuizQuestionRequest,
    QuizSetRequest,
    QuizSetResponse,
    SubmitAnswerRequest,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
    WeakConceptPublic,
    WeakestConceptPublic,
)
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter

router = APIRouter(tags=["learning"])


async def _require_enrolled(session: AsyncSession, *, user_id: int, course_id: int) -> None:
    """
    Chặn user hỏi/làm quiz về concept của môn họ KHÔNG thuộc về - cùng
    nguyên tắc ACL đã áp dụng cho Retrieval (app/retrieval/hybrid_search.py),
    áp dụng nhất quán cho Learning Assistant.
    """
    result = await session.execute(
        select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.course_id == course_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Bạn chưa thuộc lớp học chứa khái niệm này."
        )


@router.post("/v1/concepts", response_model=ConceptPublic, status_code=status.HTTP_201_CREATED)
async def create_concept(
    body: CreateConceptRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Giảng viên tự tạo 1 khái niệm cho môn mình phụ trách - xem docstring
    model Concept (app/db/models.py) về việc CHƯA tự động trích xuất.
    """
    course_result = await session.execute(select(Course).where(Course.id == body.course_id))
    course = course_result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")

    if course.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không phải giáo viên phụ trách lớp này.",
        )

    # Tính vector ngữ nghĩa của tên khái niệm NGAY TẠI ĐÂY - đây là
    # thời điểm DUY NHẤT phải trả chi phí embedding cho khái niệm này,
    # và là lúc không ai phải chờ (giảng viên tạo khái niệm là thao tác
    # hiếm). Nhờ vậy, mỗi lượt sinh viên chat sau này không tốn thêm
    # lượt gọi API nào để biết câu hỏi thuộc khái niệm gì (xem
    # app/learning/concept_matcher.py).
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
    return concept


@router.get("/v1/concepts", response_model=list[ConceptPublic])
async def list_concepts(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Danh sách khái niệm của 1 lớp - dùng cho: sinh viên chọn/sửa khái
    niệm khi hỏi gia sư, và chọn khái niệm để làm quiz.
    """
    await _require_enrolled(session, user_id=user.id, course_id=course_id)

    result = await session.execute(
        select(Concept).where(Concept.course_id == course_id).order_by(Concept.name)
    )
    return result.scalars().all()


async def _get_or_create_quiz_question(session: AsyncSession, *, concept: Concept, user_id: int) -> QuizQuestion:
    """
    Cache-first: nếu concept đã có ÍT NHẤT 1 câu hỏi trong DB, lấy lại
    câu CŨ NHẤT thay vì gọi LLM sinh mới - tiết kiệm chi phí khi nhiều
    sinh viên cùng làm quiz 1 concept (đánh đổi đã chốt cùng người dùng:
    chấp nhận lặp câu hỏi cho 1 user làm quiz nhiều lần, đổi lấy tiết
    kiệm chi phí LLM đáng kể ở quy mô nhiều người dùng).
    """
    existing = await session.execute(
        select(QuizQuestion).where(QuizQuestion.concept_id == concept.id).order_by(QuizQuestion.id).limit(1)
    )
    question = existing.scalar_one_or_none()
    if question is not None:
        return question

    try:
        generated = await generate_quiz_question(session, concept_name=concept.name, user_id=user_id)
    except QuizGenerationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    question = QuizQuestion(
        concept_id=concept.id,
        question=generated["question"],
        options=json.dumps(generated["options"], ensure_ascii=False),
        correct_index=generated["correct_index"],
        explanation=generated["explanation"],
    )
    session.add(question)
    await session.commit()
    await session.refresh(question)
    return question


@router.post("/v1/learn/quiz", response_model=QuizQuestionPublic)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_quiz_question(
    request: Request,
    body: QuizQuestionRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """Lấy 1 câu hỏi quiz cho concept chỉ định - sinh mới nếu chưa có câu nào (cache), hoặc lấy lại câu đã có."""
    concept_result = await session.execute(select(Concept).where(Concept.id == body.concept_id))
    concept = concept_result.scalar_one_or_none()
    if concept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khái niệm này.")

    await _require_enrolled(session, user_id=user.id, course_id=concept.course_id)

    question = await _get_or_create_quiz_question(session, concept=concept, user_id=user.id)

    return QuizQuestionPublic(
        id=question.id,
        concept_id=question.concept_id,
        question=question.question,
        options=json.loads(question.options),
    )


@router.post("/v1/learn/answer", response_model=AnswerResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def submit_answer(
    request: Request,
    body: SubmitAnswerRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """Nộp đáp án cho 1 câu quiz - cập nhật StudentMastery theo heuristic streak."""
    question_result = await session.execute(
        select(QuizQuestion).where(QuizQuestion.id == body.quiz_question_id)
    )
    question = question_result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy câu hỏi này.")

    concept_result = await session.execute(select(Concept).where(Concept.id == question.concept_id))
    concept = concept_result.scalar_one()  # concept_id là FK bắt buộc - luôn tồn tại nếu question tồn tại
    await _require_enrolled(session, user_id=user.id, course_id=concept.course_id)

    is_correct = body.selected_index == question.correct_index

    session.add(
        QuizAttempt(
            user_id=user.id,
            quiz_question_id=question.id,
            selected_index=body.selected_index,
            is_correct=is_correct,
        )
    )

    mastery = await get_or_create_mastery(session, user_id=user.id, concept_id=concept.id)
    apply_answer(mastery, is_correct=is_correct)

    try:
        await session.commit()
    except IntegrityError:
        # 2 request nộp đáp án gần như đồng thời cho CÙNG concept (vd
        # double-click) có thể cùng cố INSERT StudentMastery lần đầu -
        # khoá chính CẶP (user_id, concept_id) chặn trùng, rollback rồi
        # báo lỗi rõ ràng thay vì để lỗi 500 mù mờ (cùng mẫu TOCTOU đã
        # áp dụng ở app/courses/router.py).
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Có yêu cầu khác đang xử lý đồng thời, vui lòng thử lại.",
        )

    return AnswerResponse(
        is_correct=is_correct,
        correct_index=question.correct_index,
        explanation=question.explanation,
        streak=mastery.streak,
        mastered=mastery.mastered,
    )


@router.get("/v1/learn/mastery", response_model=list[MasteryPublic])
async def list_my_mastery(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """Xem tiến độ nắm vững của CHÍNH MÌNH cho 1 môn - không xem được của người khác."""
    await _require_enrolled(session, user_id=user.id, course_id=course_id)

    result = await session.execute(
        select(Concept.id, Concept.name).where(Concept.course_id == course_id)
    )
    concepts = result.all()

    mastery_rows: list[MasteryPublic] = []
    for concept_id, concept_name in concepts:
        mastery = await get_or_create_mastery(session, user_id=user.id, concept_id=concept_id)
        mastery_rows.append(
            MasteryPublic(
                concept_id=concept_id,
                concept_name=concept_name,
                streak=mastery.streak,
                n_obs=mastery.n_obs,
                n_correct=mastery.n_correct,
                mastered=mastery.mastered,
            )
        )
    await session.commit()  # get_or_create_mastery có thể đã tạo dòng mới - lưu lại
    return mastery_rows


@router.get("/v1/learn/weakest-concept", response_model=WeakestConceptPublic | None)
async def get_weakest_concept(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Khái niệm sinh viên đang yếu nhất - phục vụ Proactive AI Toast
    ("Có vẻ bạn đang gặp khó với X, hỏi gia sư không?").

    QUÉT TOÀN BỘ course sinh viên đã enroll (không giới hạn 1 course cụ
    thể) - Toast xuất hiện ở /student và /assignments, không có sẵn
    course_id để lọc, và mục đích là gợi ý CHỦ ĐỘNG bất kể đang xem môn
    nào.

    ĐIỀU KIỆN: n_obs >= 1 (đã thực sự làm ít nhất 1 câu, không gợi ý
    khái niệm chưa từng chạm tới - không có gì để nói "đang yếu"),
    accuracy < 50%, và CHƯA mastered (nếu đã mastered thì dù từng có
    giai đoạn accuracy thấp, sinh viên đã cải thiện - không nên gợi ý
    lại). Trong các concept thoả điều kiện, CHỌN accuracy THẤP NHẤT;
    hoà thì chọn n_obs LỚN HƠN (nhiều bằng chứng hơn, đáng tin hơn để
    gợi ý, tránh gợi ý dựa trên 1-2 câu ngẫu nhiên).

    Trả None nếu không có concept nào thoả điều kiện (sinh viên đang ổn,
    hoặc chưa làm quiz nào) - frontend im lặng, KHÔNG hiện Toast.
    """
    weak_concepts = await compute_weak_concepts(session, user_id=user.id)
    # Ngưỡng TRIGGER của Toast (< 50%) CỐ Ý khác ngưỡng phân loại LOW/
    # MID/HIGH dùng ở trang Tiến độ (xem app/learning/mastery_overview.py)
    # - giữ Toast nghiêm ngặt hơn để tránh làm phiền quá thường xuyên.
    candidates = [w for w in weak_concepts if w.accuracy < 0.5]
    if not candidates:
        return None

    weakest = candidates[0]  # đã sắp accuracy tăng dần, hoà thì n_obs giảm dần
    return WeakestConceptPublic(
        concept_id=weakest.concept_id,
        concept_name=weakest.concept_name,
        course_id=weakest.course_id,
        n_obs=weakest.n_obs,
        n_correct=weakest.n_correct,
        accuracy=round(weakest.accuracy, 3),
    )


# Số concept tối đa hiện trong "Gợi ý ôn tập" - khớp đúng prototype (3-5
# mục), tránh danh sách quá dài nếu sinh viên yếu ở nhiều chỗ cùng lúc.
MAX_WEAK_CONCEPTS_SHOWN = 5


@router.get("/v1/learn/mastery/overview", response_model=MasteryOverview)
async def get_mastery_overview(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Tổng quan tiến độ học tập của sinh viên trên MỌI course đã enroll -
    khác /v1/learn/mastery (yêu cầu course_id, xem 1 lớp cụ thể).

    overall_mastery và avg_mastery từng course đều dùng công thức
    SUM(n_correct)/SUM(n_obs) - KHÔNG phải trung bình cộng các tỷ lệ %
    riêng lẻ, để 1 concept đã luyện nhiều câu có trọng số đúng hơn 1
    concept mới chạm tới vài câu (xem app/profile/router.py::
    get_profile_stats() - áp dụng cùng nguyên tắc).
    """
    mastery_rows = (
        await session.execute(
            select(StudentMastery, Concept.course_id, Course.code)
            .join(Concept, Concept.id == StudentMastery.concept_id)
            .join(Course, Course.id == Concept.course_id)
            .join(Enrollment, (Enrollment.course_id == Concept.course_id) & (Enrollment.user_id == user.id))
            .where(StudentMastery.user_id == user.id, StudentMastery.n_obs >= 1)
        )
    ).all()

    total_correct = sum(m.n_correct for m, _, _ in mastery_rows)
    total_obs = sum(m.n_obs for m, _, _ in mastery_rows)
    overall_mastery = round(total_correct / total_obs, 3) if total_obs else None

    per_course_totals: dict[int, dict[str, int | str]] = {}
    for m, course_id, course_code in mastery_rows:
        entry = per_course_totals.setdefault(course_id, {"code": course_code, "correct": 0, "obs": 0})
        entry["correct"] += m.n_correct
        entry["obs"] += m.n_obs

    by_course = [
        CourseMasteryPublic(
            course_id=course_id,
            course_code=str(entry["code"]),
            avg_mastery=round(entry["correct"] / entry["obs"], 3),
        )
        for course_id, entry in per_course_totals.items()
        if entry["obs"] > 0
    ]
    by_course.sort(key=lambda c: c.avg_mastery)

    weak = await compute_weak_concepts(session, user_id=user.id)
    course_code_by_id = {course_id: str(entry["code"]) for course_id, entry in per_course_totals.items()}
    weak_concepts = [
        WeakConceptPublic(
            concept_id=w.concept_id,
            concept_name=w.concept_name,
            course_id=w.course_id,
            course_code=course_code_by_id.get(w.course_id, ""),
            accuracy=round(w.accuracy, 3),
            level="LOW" if w.accuracy < MASTERY_LOW_THRESHOLD else "MID",
        )
        for w in weak
        if w.accuracy < MASTERY_HIGH_THRESHOLD  # HIGH không đáng "gợi ý ôn tập"
    ][:MAX_WEAK_CONCEPTS_SHOWN]

    return MasteryOverview(overall_mastery=overall_mastery, by_course=by_course, weak_concepts=weak_concepts)


@router.get("/v1/learning-path", response_model=LearningPathResponsePublic)
async def get_learning_path_endpoint(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Lấy lộ trình học tập cho sinh viên trong 1 course.

    Trả về:
    - Danh sách concepts với tiến độ của sinh viên
    - Status của từng concept (completed/in_progress/available/locked/not_started)
    - Gợi ý concept tiếp theo nên học

    Khác với:
    - /v1/learn/mastery: xem mastery CHI TIẾT cho 1 course
    - /v1/learn/mastery/overview: TỔNG QUAN mọi course
    - /v1/learn/weakest-concept: khái niệm yếu NHẤT cho Toast
    """
    # Gọi THẲNG get_learning_path() của app/learning/learning_path.py thay vì
    # giữ một bản sao logic ngay trong router. Trước đây router có helper
    # _get_learning_path_data() chép lại gần như y hệt module kia, và cái giá
    # đã phải trả thật: 2 bug logic (gợi ý "review" không bao giờ khớp, và màn
    # hình gợi ý TRỐNG với sinh viên mới) phải sửa ở CẢ HAI nơi, một lần patch
    # còn trượt vì comment hai bên lệch nhau một chữ. Router giờ chỉ còn giữ
    # phần thuộc về tầng HTTP: bắt ValueError -> 400 và convert dataclass sang
    # Pydantic. Đánh đổi: thêm một lớp gọi hàm, nhưng logic học tập chỉ còn
    # MỘT nguồn sự thật để sửa và để test.
    try:
        result = await get_learning_path(session, course_id=course_id, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Convert dataclass to Pydantic model
    concepts = [
        ConceptProgressPublic(
            id=c.id,
            name=c.name,
            complexity=c.complexity,
            mastery=c.mastery,
            status=c.status.value if hasattr(c.status, 'value') else c.status,
            prerequisites=c.prerequisites,
            estimated_time_minutes=c.estimated_time_minutes,
        )
        for c in result.concepts
    ]

    recommendations = [
        RecommendationPublic(
            type=r.type,
            concept_id=r.concept_id,
            concept_name=r.concept_name,
            reason=r.reason,
            priority=r.priority,
        )
        for r in result.recommendations
    ]

    return LearningPathResponsePublic(
        course_id=result.course_id,
        course_name=result.course_name,
        concepts=concepts,
        recommendations=recommendations,
    )


@router.post("/v1/learn/quiz-set", response_model=QuizSetResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_quiz_set(
    request: Request,
    body: QuizSetRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Lấy MỘT BỘ câu hỏi để sinh viên làm liền mạch rồi nộp 1 lần.

    KHÁC /v1/learn/quiz (1 câu): làm từng câu rồi nộp ngay khiến mạch
    làm bài bị cắt vụn, và không có cảm giác "đang làm bài kiểm tra".
    Bộ đề cho phép xem lại/đổi đáp án trước khi chốt.

    Ưu tiên TÁI DÙNG câu đã có trong kho (cùng lý do cache-first ở
    _get_or_create_quiz_question: nhiều sinh viên cùng ôn 1 khái niệm
    thì không việc gì phải trả tiền LLM lặp lại). Chỉ sinh bù phần
    THIẾU, và sinh trong 1 lượt gọi duy nhất để các câu không trùng
    nhau (xem generate_quiz_questions_batch).
    """
    concept_result = await session.execute(select(Concept).where(Concept.id == body.concept_id))
    concept = concept_result.scalar_one_or_none()
    if concept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy khái niệm này.")

    await _require_enrolled(session, user_id=user.id, course_id=concept.course_id)

    existing = (
        await session.execute(
            select(QuizQuestion)
            .where(QuizQuestion.concept_id == concept.id)
            .order_by(QuizQuestion.id)
            .limit(body.num_questions)
        )
    ).scalars().all()

    questions = list(existing)
    missing = body.num_questions - len(questions)

    if missing > 0:
        try:
            generated_list = await generate_quiz_questions_batch(
                session, concept_name=concept.name, user_id=user.id, count=missing
            )
        except QuizGenerationError as e:
            # Kho đã có sẵn vài câu thì vẫn dùng được - chỉ báo lỗi khi
            # KHÔNG có câu nào để làm, tránh chặn cả lượt ôn tập chỉ vì
            # không sinh bù được.
            if not questions:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
            generated_list = []

        for generated in generated_list:
            question = QuizQuestion(
                concept_id=concept.id,
                question=generated["question"],
                options=json.dumps(generated["options"], ensure_ascii=False),
                correct_index=generated["correct_index"],
                explanation=generated["explanation"],
            )
            session.add(question)
            await session.flush()
            questions.append(question)

        await session.commit()

    return QuizSetResponse(
        concept_id=concept.id,
        concept_name=concept.name,
        questions=[
            QuizQuestionPublic(
                id=q.id,
                concept_id=q.concept_id,
                question=q.question,
                options=json.loads(q.options),
            )
            for q in questions
        ],
    )


@router.post("/v1/learn/answers", response_model=SubmitAnswersResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def submit_answers(
    request: Request,
    body: SubmitAnswersRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Nộp CẢ BỘ đáp án một lần (sau khi sinh viên làm xong toàn bộ).

    Mastery được cập nhật cho TỪNG câu theo đúng thứ tự làm bài - dùng
    lại apply_answer() y hệt luồng 1 câu, không viết lại heuristic
    streak (nếu tính khác đi thì cùng 1 sinh viên sẽ có 2 mức mastery
    khác nhau tuỳ họ chọn cách nộp nào, vô lý).
    """
    question_ids = [a.quiz_question_id for a in body.answers]
    questions = (
        await session.execute(select(QuizQuestion).where(QuizQuestion.id.in_(question_ids)))
    ).scalars().all()
    questions_by_id = {q.id: q for q in questions}

    if len(questions_by_id) != len(set(question_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Có câu hỏi không tồn tại."
        )

    # Mọi câu trong 1 lượt nộp phải cùng 1 concept - bộ đề được lấy theo
    # concept nên trộn nhiều concept nghĩa là client gửi sai/cố tình.
    concept_ids = {q.concept_id for q in questions}
    if len(concept_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Các câu hỏi trong một lượt nộp phải thuộc cùng một khái niệm.",
        )

    concept = (
        await session.execute(select(Concept).where(Concept.id == concept_ids.pop()))
    ).scalar_one()
    await _require_enrolled(session, user_id=user.id, course_id=concept.course_id)

    mastery = await get_or_create_mastery(session, user_id=user.id, concept_id=concept.id)

    results: list[QuizAnswerResult] = []
    score = 0
    for answer in body.answers:
        question = questions_by_id[answer.quiz_question_id]
        is_correct = answer.selected_index == question.correct_index
        if is_correct:
            score += 1

        session.add(
            QuizAttempt(
                user_id=user.id,
                quiz_question_id=question.id,
                selected_index=answer.selected_index,
                is_correct=is_correct,
            )
        )
        apply_answer(mastery, is_correct=is_correct)

        results.append(
            QuizAnswerResult(
                quiz_question_id=question.id,
                question=question.question,
                options=json.loads(question.options),
                selected_index=answer.selected_index,
                correct_index=question.correct_index,
                is_correct=is_correct,
                explanation=question.explanation,
            )
        )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Có yêu cầu khác đang xử lý đồng thời, vui lòng thử lại.",
        )

    return SubmitAnswersResponse(
        score=score,
        total=len(body.answers),
        results=results,
        streak=mastery.streak,
        mastered=mastery.mastered,
    )
