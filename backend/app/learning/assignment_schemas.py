from datetime import datetime

from pydantic import BaseModel, Field


class CreateAssignmentRequest(BaseModel):
    course_id: int
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    due_at: datetime | None = None
    # Các khái niệm cần ra đề - hệ thống lấy câu hỏi đã sinh sẵn cho
    # từng khái niệm (hoặc sinh mới nếu chưa có), mỗi khái niệm 1 câu.
    concept_ids: list[int] = Field(min_length=1)


class AssignmentPublic(BaseModel):
    id: int
    course_id: int
    title: str
    description: str | None
    due_at: datetime | None
    question_count: int
    # Trạng thái của CHÍNH sinh viên đang gọi API (None nếu là giảng viên xem)
    my_score: int | None = None
    my_total: int | None = None
    submitted: bool = False


class AssignmentQuestionPublic(BaseModel):
    """Câu hỏi hiển thị cho sinh viên làm bài - KHÔNG kèm đáp án đúng."""

    quiz_question_id: int
    ord: int
    question: str
    options: list[str]


class AssignmentDetail(BaseModel):
    id: int
    title: str
    description: str | None
    due_at: datetime | None
    questions: list[AssignmentQuestionPublic]


class SubmitAssignmentAnswer(BaseModel):
    quiz_question_id: int
    selected_index: int = Field(ge=0, le=3)


class SubmitAssignmentRequest(BaseModel):
    answers: list[SubmitAssignmentAnswer]


class AnswerResult(BaseModel):
    quiz_question_id: int
    is_correct: bool
    correct_index: int
    explanation: str


class SubmitAssignmentResponse(BaseModel):
    score: int
    total: int
    results: list[AnswerResult]


class StudentResultSummary(BaseModel):
    """Kết quả 1 sinh viên - CHỈ giảng viên phụ trách lớp xem được."""

    user_id: int
    full_name: str
    score: int
    total: int
    submitted_at: datetime


class ConceptDifficulty(BaseModel):
    """Khái niệm nào cả lớp làm sai nhiều nhất - giá trị sư phạm chính."""

    concept_id: int
    concept_name: str
    correct_count: int
    total_count: int
    accuracy: float  # 0.0 - 1.0


class AssignmentResults(BaseModel):
    assignment_id: int
    title: str
    submitted_count: int
    enrolled_count: int
    average_score: float
    total_questions: int
    students: list[StudentResultSummary]
    concept_difficulty: list[ConceptDifficulty]
