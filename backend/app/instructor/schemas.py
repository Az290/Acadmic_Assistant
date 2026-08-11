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


class StudentNeedingSupport(BaseModel):
    """
    1 sinh viên đang gặp khó trong lớp.

    THAY ĐỔI CHÍNH SÁCH RIÊNG TƯ CÓ CHỦ Ý (đã thảo luận và chốt cùng
    người dùng): trước đây Dashboard giảng viên CHỈ hiển thị số liệu
    tổng hợp ẩn danh. Từ đây, giảng viên xem được TÊN + tiến độ học tập
    của từng sinh viên yếu - vì không biết ai đang gặp khó thì không
    thể hỗ trợ kịp thời, mà hỗ trợ kịp thời chính là mục đích của cả hệ
    thống.

    RANH GIỚI VẪN GIỮ NGUYÊN: chỉ dữ liệu SƯ PHẠM (mastery, khái niệm
    yếu, số câu đã hỏi). TUYỆT ĐỐI KHÔNG lộ nội dung câu hỏi, câu trả
    lời, hay lịch sử hội thoại của sinh viên - những thứ đó vẫn không
    có endpoint nào trả về cho giảng viên.
    """

    user_id: int
    full_name: str
    mastery: float
    weakest_concept_name: str | None  # None nếu mọi concept đều đã mastered
    question_count: int


class MasteryDistributionBucket(BaseModel):
    """1 cột trong biểu đồ phân bố - label dạng '0-20%', '20-40%'..."""

    label: str
    student_count: int


class ClassAnalytics(BaseModel):
    """
    Phân tích 1 lớp cụ thể - ai đang cần giúp, phân bố trình độ ra sao.

    students_without_data: sinh viên CHƯA làm quiz nào (n_obs = 0) -
    tách riêng, KHÔNG tính vào phân bố và KHÔNG đưa vào danh sách cần
    hỗ trợ. Lý do: mastery 0% vì "chưa học gì" hoàn toàn khác 0% vì
    "học mà không hiểu" - gộp chung sẽ khiến giảng viên hiểu sai tình
    hình lớp và hỗ trợ nhầm người.
    """

    course_id: int
    total_students: int
    students_with_data: int
    students_without_data: int
    avg_mastery: float | None  # None nếu chưa sinh viên nào có dữ liệu
    needing_support_count: int
    distribution: list[MasteryDistributionBucket]
    students_needing_support: list[StudentNeedingSupport]


class PopularConcept(BaseModel):
    """
    1 dòng trong trang "Câu hỏi phổ biến" - gom theo KHÁI NIỆM, không
    phải theo chuỗi câu hỏi thô.

    VÌ SAO GOM THEO KHÁI NIỆM: sinh viên diễn đạt cùng 1 thắc mắc bằng
    vô số cách khác nhau ("SGD khác GD sao?", "tại sao SGD nhanh hơn?",
    "so sánh 2 thuật toán tối ưu này")  - gom theo chuỗi văn bản sẽ ra
    hàng trăm nhóm 1-phần-tử vô nghĩa. Gom theo concept_id (đã có sẵn
    từ Gap Analysis) cho ra nhóm đúng bản chất và tái dùng hạ tầng cũ.

    positive_rate = None nghĩa là CHƯA ĐỦ DỮ LIỆU đánh giá (ít hơn
    MIN_FEEDBACK_FOR_RATE phiếu) - KHÁC HẲN 0.0 (đã có phiếu và toàn
    bộ đều tiêu cực). Không được hiển thị "0%" cho trường hợp đầu.
    """

    concept_id: int
    concept_name: str
    question_count: int
    avg_retrieval_similarity: float | None  # None nếu chưa câu nào tra cứu tài liệu
    feedback_count: int
    positive_rate: float | None
    # True khi hội đủ MỌI điều kiện cảnh báo (xem MIN_* trong router.py) -
    # dấu hiệu kho tài liệu có thể thiếu nội dung về chủ đề này.
    needs_attention: bool


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
