from datetime import datetime

from pydantic import BaseModel


class EvalRunSummary(BaseModel):
    """1 dòng trong danh sách lịch sử các lượt eval - KHÔNG kèm chi tiết
    từng câu (xem EvalRunDetail), đủ để vẽ biểu đồ xu hướng theo thời gian."""

    id: int
    git_commit_hash: str | None
    model_version: str
    dataset_version: str
    total_cases: int
    errors: int
    category_accuracy: float
    avg_recall_at_k: float | None
    avg_judge_score: float | None
    judge_cases_scored: int
    created_at: datetime

    # protected_namespaces=(): tắt cảnh báo Pydantic về field "model_version"
    # trùng tiền tố "model_" dành riêng cho nội bộ BaseModel - không có
    # xung đột thật, chỉ là trùng tên.
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class EvalCaseResultPublic(BaseModel):
    id: int
    case_id: str
    expected_category: str
    actual_category: str | None
    category_match: bool | None
    recall_at_k: float | None
    judge_score: int | None
    judge_reasoning: str | None
    answer_preview: str | None
    latency_s: float | None
    error: str | None

    model_config = {"from_attributes": True}


class EvalRunDetail(EvalRunSummary):
    """Chi tiết 1 lượt eval CỤ THỂ - kèm toàn bộ kết quả từng câu hỏi mẫu."""

    cases: list[EvalCaseResultPublic]
