"""
Tải "hồ sơ học tập" của 1 sinh viên trong 1 lớp: danh sách khái niệm
của lớp (kèm vector ngữ nghĩa) + mức độ nắm vững từng khái niệm.

THIẾT KẾ VÌ TỐC ĐỘ: gom TẤT CẢ vào ĐÚNG 1 lượt truy vấn database, và
lượt truy vấn này được caller chạy SONG SONG với Guardrail + Router
(xem app/academic_agent/agent.py) - không nằm nối tiếp trên đường đi
của người dùng, nên gần như không thêm độ trễ nào.

Tải TOÀN BỘ mastery của sinh viên trong lớp (thay vì chỉ khái niệm
đang hỏi) là CÓ CHỦ Ý: tại thời điểm chạy truy vấn này, hệ thống CHƯA
biết câu hỏi thuộc khái niệm nào (việc đó cần vector câu hỏi, tính ở
bước sau). Mỗi lớp chỉ có vài chục khái niệm nên tải hết vẫn rẻ hơn
nhiều so với chờ biết khái niệm rồi mới truy vấn (thêm 1 round-trip
tuần tự).
"""

import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept, Enrollment, QuizAttempt, QuizQuestion, StudentMastery


@dataclass
class MasteryInfo:
    mastered: bool = False
    n_obs: int = 0
    n_correct: int = 0
    streak: int = 0


@dataclass
class RecentMistake:
    """
    Câu quiz SAI gần đây nhất của sinh viên - dùng để trả lời khi sinh
    viên hỏi kiểu "giải thích câu vừa rồi tôi làm sai" mà KHÔNG nêu rõ
    câu nào (xem build_recent_mistake_block() trong prompts.py). Đủ
    thông tin để LLM giải thích trực tiếp, không cần hỏi lại.
    """

    quiz_question_id: int
    question: str
    options: list[str]
    your_answer: str | None
    correct_answer: str | None
    explanation: str
    concept_name: str


@dataclass
class StudentContext:
    # (concept_id, name, embedding) - đúng định dạng concept_matcher cần
    concepts: list[tuple[int, str, list[float] | None]] = field(default_factory=list)
    mastery_by_concept: dict[int, MasteryInfo] = field(default_factory=dict)
    recent_mistake: RecentMistake | None = None

    def mastery_for(self, concept_id: int) -> MasteryInfo:
        """Chưa từng làm quiz khái niệm này -> trả về bản ghi rỗng (n_obs=0), không phải lỗi."""
        return self.mastery_by_concept.get(concept_id, MasteryInfo())


async def load_student_context(
    session: AsyncSession, *, user_id: int, course_id: int | None = None
) -> StudentContext:
    """
    course_id: giới hạn trong 1 lớp cụ thể nếu người dùng đã chọn lớp;
    None -> lấy khái niệm của MỌI lớp sinh viên đang theo học.

    Điều kiện lọc theo `enrollment` là BẮT BUỘC (không phải tuỳ chọn):
    cùng nguyên tắc ACL đã áp dụng cho Retrieval - sinh viên không được
    thấy khái niệm của lớp mình không thuộc về, kể cả gián tiếp qua
    việc gia sư nhắc tới tên khái niệm đó.
    """
    concept_query = select(Concept.id, Concept.name, Concept.embedding).where(
        Concept.course_id.in_(
            select(Enrollment.course_id).where(Enrollment.user_id == user_id)
        )
    )
    if course_id is not None:
        concept_query = concept_query.where(Concept.course_id == course_id)

    concept_rows = (await session.execute(concept_query)).all()

    # Câu làm sai gần đây nhất - tải LUÔN kể cả khi lớp CHƯA có concept
    # nào enroll match (concept_rows rỗng vẫn có thể có mistake nếu
    # course_id=None và sinh viên có mistake ở lớp khác) - vì vậy bước
    # này KHÔNG return sớm theo `if not concept_rows` như trước, phải
    # tách riêng thành helper chạy độc lập.
    recent_mistake = await _load_recent_mistake(session, user_id=user_id, course_id=course_id)

    if not concept_rows:
        return StudentContext(recent_mistake=recent_mistake)

    concept_ids = [row[0] for row in concept_rows]
    mastery_rows = (
        await session.execute(
            select(StudentMastery).where(
                StudentMastery.user_id == user_id,
                StudentMastery.concept_id.in_(concept_ids),
            )
        )
    ).scalars().all()

    return StudentContext(
        concepts=[(row[0], row[1], row[2]) for row in concept_rows],
        mastery_by_concept={
            m.concept_id: MasteryInfo(
                mastered=m.mastered, n_obs=m.n_obs, n_correct=m.n_correct, streak=m.streak
            )
            for m in mastery_rows
        },
        recent_mistake=recent_mistake,
    )


async def _load_recent_mistake(
    session: AsyncSession, *, user_id: int, course_id: int | None
) -> RecentMistake | None:
    """
    Câu QuizAttempt SAI mới nhất của sinh viên - course_id giới hạn
    đúng lớp đang chat (join qua Concept.course_id) nếu đã biết, None
    thì lấy mới nhất trên MỌI lớp (đủ dùng khi Conversation chưa gắn
    lớp nào). CHỈ 1 query nhỏ (limit 1), chạy chung batch song song với
    Guardrail/Router như phần còn lại của load_student_context - không
    thêm round-trip nối tiếp nào.
    """
    query = (
        select(QuizAttempt, QuizQuestion, Concept.name)
        .join(QuizQuestion, QuizQuestion.id == QuizAttempt.quiz_question_id)
        .join(Concept, Concept.id == QuizQuestion.concept_id)
        .where(QuizAttempt.user_id == user_id, QuizAttempt.is_correct.is_(False))
        .order_by(QuizAttempt.attempted_at.desc())
        .limit(1)
    )
    if course_id is not None:
        query = query.where(Concept.course_id == course_id)

    row = (await session.execute(query)).first()
    if row is None:
        return None

    attempt, question, concept_name = row
    options = json.loads(question.options)
    return RecentMistake(
        quiz_question_id=question.id,
        question=question.question,
        options=options,
        your_answer=options[attempt.selected_index] if 0 <= attempt.selected_index < len(options) else None,
        correct_answer=options[question.correct_index] if 0 <= question.correct_index < len(options) else None,
        explanation=question.explanation,
        concept_name=concept_name,
    )
