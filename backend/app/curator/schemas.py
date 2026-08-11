"""
Schema CỐ ĐỊNH cho kết quả từng bước Curator Agent - dùng chung cho cả
3 module con (injection_scan, quality_gate, dedup) và bộ điều phối
(curator.py), để backend luôn tạo ra ĐÚNG 1 cấu trúc, frontend chỉ cần
render theo schema mà không phải tự suy luận/parse chuỗi.

status CHỈ có 2 giá trị (không có "fail"): Curator KHÔNG BAO GIỜ tự
chặn tài liệu - "fail" sẽ ngầm gợi ý có 1 mức độ nghiêm trọng hơn cần
xử lý khác "warn", trong khi thực tế cả 2 tình huống đều dẫn tới CÙNG
1 hành động (con người xem và tự quyết định lúc duyệt - HITL).
"""

from typing import Literal

from pydantic import BaseModel

CuratorStepStatus = Literal["pass", "warn"]


class CuratorStepResult(BaseModel):
    status: CuratorStepStatus
    detail: str


class CuratorReport(BaseModel):
    """Toàn bộ kết quả Curator cho 1 tài liệu - lưu dạng JSON trong Document.curator_notes."""

    injection_scan: CuratorStepResult
    quality_gate: CuratorStepResult
    dedup: CuratorStepResult
