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
from app.db.models import AppUser, Concept, Course, Enrollment, QuizAttempt, QuizQuestion
from app.db.session import get_db
from app.ingestion.embedder import embed_texts
from app.learning.mastery import apply_answer, get_or_create_mastery
from app.learning.quiz_generator import QuizGenerationError, generate_quiz_question
from app.learning.schemas import (
    AnswerResponse,
    ConceptPublic,
    CreateConceptRequest,
    MasteryPublic,
    QuizQuestionPublic,
    QuizQuestionRequest,
    SubmitAnswerRequest,
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
