"""
Bảng giá GHÉ CỨNG (hard-code) cho từng model đang dùng trong dự án -
QUYẾT ĐỊNH CÓ CHỦ Ý: OpenAI không có endpoint công khai trả về giá
theo thời gian thực, nên không có cách nào "tự động" lấy giá thật -
chỉ có 2 lựa chọn: ghé cứng (đơn giản, cần tự cập nhật khi giá đổi)
hoặc không tính được gì cả. Chọn ghé cứng.

Giá tính theo $ / 1 TRIỆU token, lấy từ trang giá chính thức của
OpenAI tại THỜI ĐIỂM code (2026-08) - CẦN CẬP NHẬT TAY nếu OpenAI đổi
giá, không có cơ chế tự động cảnh báo khi giá cũ lỗi thời.
"""

from dataclasses import dataclass


@dataclass
class ModelPricing:
    input_per_million: float
    output_per_million: float


# Chỉ liệt kê các model THẬT SỰ đang dùng trong dự án (xem
# app/academic_agent/prompts.py, app/router_agent/classifier.py,
# app/ingestion/embedder.py) - không liệt kê model không dùng tới để
# tránh nhầm lẫn.
PRICING: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(input_per_million=0.15, output_per_million=0.60),
    "text-embedding-3-large": ModelPricing(input_per_million=0.13, output_per_million=0.0),
    "text-embedding-3-small": ModelPricing(input_per_million=0.02, output_per_million=0.0),
    "omni-moderation-latest": ModelPricing(input_per_million=0.0, output_per_million=0.0),  # miễn phí
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    """
    Trả về 0.0 cho model KHÔNG có trong bảng giá (thay vì lỗi) - một
    model mới thêm vào code mà quên cập nhật giá không nên làm sập cả
    Dashboard, chỉ nên thiếu chính xác ở đúng phần đó (chấp nhận được,
    dễ phát hiện hơn nhiều so với lỗi 500).
    """
    pricing = PRICING.get(model)
    if pricing is None:
        return 0.0
    return (input_tokens / 1_000_000) * pricing.input_per_million + (
        output_tokens / 1_000_000
    ) * pricing.output_per_million
