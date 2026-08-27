from datetime import datetime

from pydantic import BaseModel, Field


class CreateAssignmentRequest(BaseModel):
    course_id: int
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    due_at: datetime | None = None
    # Các khái niệm cần ra đề - hệ thống lấy câu hỏi đã sinh sẵn cho
    # từng khái niệm (hoặc sinh mới nếu chưa có), mỗi khái niệm 1 câu.
    # CHỈ dùng khi quiz_question_ids KHÔNG được truyền lên (xem bên dưới) -
    # giữ để tương thích ngược với luồng cũ (giao bài trực tiếp không qua bước duyệt).
    concept_ids: list[int] = Field(default_factory=list)
    # Danh sách câu hỏi CỤ THỂ đã được giảng viên xem/sửa/duyệt (luồng mới -
    # xem POST /v1/assignments/generate-questions). Khi có mặt, ĐƯỢC ƯU TIÊN
    # tuyệt đối: dùng ĐÚNG các câu hỏi này theo đúng thứ tự, KHÔNG tự sinh
    # thêm gì cả - tôn trọng nội dung giảng viên đã duyệt.
    quiz_question_ids: list[int] | None = None


class GenerateQuestionsRequest(BaseModel):
    """
    Sinh NHÁP câu hỏi để giảng viên xem/sửa/duyệt trước khi giao bài -
    KHÁC với CreateAssignmentRequest.concept_ids (tự sinh + giao luôn).

    Câu hỏi sinh ra được LƯU vào bảng quiz_question (có id thật) nhưng
    CHƯA gắn với assignment nào - giảng viên có thể sửa qua PATCH
    /v1/quiz-questions/{id} rồi mới chọn để giao qua POST /v1/assignments
    với quiz_question_ids.
    """

    course_id: int
    concept_ids: list[int] = Field(min_length=1)
    # Số câu hỏi MUỐN SINH cho MỖI khái niệm - không dùng "total_questions"
    # chia đều vì số câu không chia hết cho số khái niệm sẽ gây mơ hồ (concept
    # nào được ít hơn?). Rõ ràng, dễ hiểu với giảng viên: "mỗi khái niệm N câu".
    # Trần 30: đủ cho 1 đề kiểm tra dài, vẫn chặn được yêu cầu vô lý
    # (sinh 500 câu = 1 lượt LLM khổng lồ + chờ rất lâu + tốn chi phí).
    num_questions_per_concept: int = Field(default=1, ge=1, le=30)


class GeneratedQuizQuestionPublic(BaseModel):
    """1 câu hỏi nháp vừa sinh - kèm ĐÁP ÁN ĐÚNG vì đây là màn hình DUYỆT của giảng viên (khác AssignmentQuestionPublic của sinh viên)."""

    id: int
    concept_id: int
    concept_name: str
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class UpdateQuizQuestionRequest(BaseModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(default="")


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


class CreateQuizQuestionRequest(BaseModel):
    """Giảng viên TỰ SOẠN 1 câu hỏi (không qua AI) để thêm vào đề đang duyệt."""

    concept_id: int
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(default="")


class RegenerateQuizQuestionRequest(BaseModel):
    """
    Góp ý để AI sinh lại 1 câu hỏi - vd "đáp án đúng đang sai, phải là B",
    "câu này trùng câu 2", "hỏi về cách dùng thực tế thay vì cú pháp".
    """

    feedback: str = Field(min_length=1, max_length=500)
