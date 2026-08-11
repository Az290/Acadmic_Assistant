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


class CostSummary(BaseModel):
    """
    Chi phí LLM thật đã phát sinh cho lớp - CHỈ đo được bước sinh câu
    trả lời (bước tốn kém nhất), xem giới hạn đã nói rõ trong
    app/academic_agent/agent.py.
    """

    total_messages_measured: int  # số câu trả lời CÓ dữ liệu đo (message cũ trước khi có tính năng này sẽ không có)
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_cost_per_message_usd: float
    # Dự báo chi phí/tháng nếu duy trì mức dùng hiện tại - ngoại suy
    # ĐƠN GIẢN (tuyến tính) từ trung bình/câu, KHÔNG tính tới mùa thi
    # hay biến động thực tế - chỉ mang tính tham khảo thô.
    projected_monthly_usd_per_100_students: float


class PipelineStepTiming(BaseModel):
    step: str
    avg_ms: float
    p95_ms: float


class PipelineTiming(BaseModel):
    """Thời gian trung bình từng bước - biết bước nào đang là điểm nghẽn bằng số liệu thật."""

    total_messages_measured: int
    steps: list[PipelineStepTiming]
    avg_total_ms: float


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
