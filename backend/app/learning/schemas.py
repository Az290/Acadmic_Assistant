from pydantic import BaseModel, Field


class CreateConceptRequest(BaseModel):
    course_id: int
    name: str = Field(min_length=1, max_length=200)
    complexity: int = Field(default=3, ge=1, le=5)


class ConceptPublic(BaseModel):
    id: int
    course_id: int
    name: str
    complexity: int

    model_config = {"from_attributes": True}


class QuizQuestionRequest(BaseModel):
    concept_id: int


class QuizQuestionPublic(BaseModel):
    """
    Trả về cho client KHÔNG kèm correct_index - lộ đáp án ngay trong
    response thì quiz mất hết ý nghĩa. Client chỉ biết đáp án đúng sau
    khi gọi /v1/learn/answer (xem AnswerResponse bên dưới).
    """

    id: int
    concept_id: int
    question: str
    options: list[str]


class SubmitAnswerRequest(BaseModel):
    quiz_question_id: int
    selected_index: int = Field(ge=0, le=3)


class AnswerResponse(BaseModel):
    is_correct: bool
    correct_index: int
    explanation: str
    streak: int
    mastered: bool


class MasteryPublic(BaseModel):
    concept_id: int
    concept_name: str
    streak: int
    n_obs: int
    n_correct: int
    mastered: bool


class WeakestConceptPublic(BaseModel):
    """
    Khái niệm sinh viên đang YẾU NHẤT (accuracy thấp nhất trong số các
    concept đã có ít nhất 1 lượt quan sát và CHƯA mastered) - dùng cho
    Proactive AI Toast gợi ý "Hỏi gia sư" (xem app/learning/router.py::
    get_weakest_concept()).
    """

    concept_id: int
    concept_name: str
    course_id: int
    n_obs: int
    n_correct: int
    accuracy: float


class CourseMasteryPublic(BaseModel):
    course_id: int
    course_code: str
    avg_mastery: float  # SUM(n_correct)/SUM(n_obs) trên mọi concept của course này


class WeakConceptPublic(BaseModel):
    concept_id: int
    concept_name: str
    course_id: int
    course_code: str
    accuracy: float
    level: str  # "LOW" | "MID" - concept HIGH không đáng để "gợi ý ôn tập"


class MasteryOverview(BaseModel):
    """
    Trang Tiến độ học tập (/mastery) - tổng thể + theo môn + danh sách
    gợi ý ôn tập, KHÁC WeakestConceptPublic (Toast chỉ cần 1 kết quả).
    """

    overall_mastery: float | None  # None nếu chưa có lượt quan sát nào
    by_course: list[CourseMasteryPublic]
    weak_concepts: list[WeakConceptPublic]
