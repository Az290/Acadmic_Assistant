from pydantic import BaseModel


class CategoryCount(BaseModel):
    category: str
    count: int


class InsufficientContextRate(BaseModel):
    total_rag_questions: int
    insufficient_count: int
    rate: float  # 0.0 - 1.0


class SecurityAlertSummary(BaseModel):
    blocked_by: str  # "rules" hoặc "moderation"
    count: int


class ConceptGap(BaseModel):
    """
    Một "điểm mù tài liệu" cụ thể: sinh viên hỏi về khái niệm này bao
    nhiêu lần, trong đó bao nhiêu lần hệ thống KHÔNG tìm được tài liệu
    phù hợp để trả lời.
    """

    concept_id: int | None  # None = câu hỏi không khớp khái niệm nào giảng viên đã tạo
    concept_name: str
    total_questions: int
    unanswered_questions: int
    gap_rate: float  # 0.0 - 1.0, càng cao càng thiếu tài liệu


class InstructorAnalytics(BaseModel):
    """
    Thống kê TỔNG HỢP theo lớp - KHÔNG cá nhân hoá, không lộ nội dung
    hội thoại riêng của từng sinh viên (xem docstring router.py).
    """

    course_id: int
    total_messages: int
    category_breakdown: list[CategoryCount]
    insufficient_context: InsufficientContextRate
    security_alerts: list[SecurityAlertSummary]
    # Xếp theo mức độ thiếu tài liệu giảm dần - chủ đề cần bổ sung
    # tài liệu gấp nhất nằm đầu danh sách.
    concept_gaps: list[ConceptGap] = []
