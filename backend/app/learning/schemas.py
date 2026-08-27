from pydantic import BaseModel, Field


class CreateConceptRequest(BaseModel):
    course_id: int
    name: str = Field(min_length=1, max_length=200)
    complexity: int = Field(default=3, ge=1, le=5)
    prerequisites: list[int] = Field(default_factory=list)  # Danh sách concept_id cần học trước


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


# ---------- Learning Path ----------

class ConceptProgressPublic(BaseModel):
    """Tiến độ của 1 concept trong learning path."""
    id: int
    name: str
    complexity: int
    mastery: float | None  # None = chưa có dữ liệu
    status: str  # "completed" | "in_progress" | "available" | "locked" | "not_started"
    prerequisites: list[int]
    estimated_time_minutes: int


class RecommendationPublic(BaseModel):
    """Gợi ý cho sinh viên."""
    type: str  # "next_learn" | "continue" | "review"
    concept_id: int
    concept_name: str
    reason: str
    priority: int


class LearningPathResponsePublic(BaseModel):
    """Response cho learning path endpoint."""
    course_id: int
    course_name: str
    concepts: list[ConceptProgressPublic]
    recommendations: list[RecommendationPublic]


class QuizSetRequest(BaseModel):
    """
    Lấy MỘT BỘ câu hỏi để làm liền mạch rồi nộp 1 lần - khác
    QuizQuestionRequest (1 câu/1 lượt nộp, gây gián đoạn mạch làm bài).
    """

    concept_id: int
    # Trần 20: đủ cho 1 lượt ôn tập, chặn yêu cầu vô lý (sinh 200 câu
    # = rất nhiều lượt gọi LLM nếu kho chưa có sẵn).
    num_questions: int = Field(default=5, ge=1, le=20)


class QuizSetResponse(BaseModel):
    concept_id: int
    concept_name: str
    questions: list[QuizQuestionPublic]


class SubmitAnswersRequest(BaseModel):
    """Nộp CẢ BỘ đáp án một lần, sau khi sinh viên làm xong toàn bộ."""

    answers: list[SubmitAnswerRequest] = Field(min_length=1)


class QuizAnswerResult(BaseModel):
    """Kết quả 1 câu trong bộ - kèm đủ dữ liệu để hiển thị lại đề bài
    và đáp án đã chọn, tránh frontend phải tự ghép từ nhiều nguồn."""

    quiz_question_id: int
    question: str
    options: list[str]
    selected_index: int
    correct_index: int
    is_correct: bool
    explanation: str


class SubmitAnswersResponse(BaseModel):
    score: int
    total: int
    results: list[QuizAnswerResult]
    # Mastery SAU KHI đã tính cả bộ - chỉ trả 1 lần ở cuối thay vì sau
    # từng câu, đúng với việc nộp theo bộ.
    streak: int
    mastered: bool
