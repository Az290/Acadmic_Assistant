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
