"""
Điều phối 2 lớp phòng thủ: rule-based (rules.py, chạy trước - rẻ,
tức thì, không gọi mạng) rồi tới Moderation API (moderation.py, chỉ
gọi nếu rule-based không chặn - vẫn miễn phí nhưng có round-trip
mạng, không cần tốn nếu đã chặn được sớm).

Áp dụng CẢ 2 CHIỀU:
- check_input(): kiểm tra câu hỏi user gửi lên TRƯỚC KHI đưa vào
  Retrieval/Agent.
- check_output(): kiểm tra câu trả lời AI sinh ra SAU KHI có kết quả,
  TRƯỚC KHI trả về client - lớp phòng thủ bổ sung, không thay thế cho
  việc is_solution=FALSE đã chặn đáp án ở tầng dữ liệu (xem
  app/retrieval/hybrid_search.py).
"""

from dataclasses import dataclass

from app.guardrail.moderation import check_moderation
from app.guardrail.rules import check_injection_patterns


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str | None = None
    blocked_by: str | None = None  # "rules" hoặc "moderation" - để biết lớp nào chặn, phục vụ debug/log


def check_input(text: str) -> GuardrailResult:
    """
    Kiểm tra câu hỏi/nội dung đầu vào từ user.

    Thứ tự có chủ đích: rule-based TRƯỚC (không tốn gì, tức thì) - nếu
    đã đủ để chặn thì KHÔNG cần gọi Moderation API nữa, tiết kiệm 1
    round-trip mạng không cần thiết.
    """
    injection_reason = check_injection_patterns(text)
    if injection_reason is not None:
        return GuardrailResult(allowed=False, reason=injection_reason, blocked_by="rules")

    moderation_reason = check_moderation(text)
    if moderation_reason is not None:
        return GuardrailResult(allowed=False, reason=moderation_reason, blocked_by="moderation")

    return GuardrailResult(allowed=True)


def check_output(text: str) -> GuardrailResult:
    """
    Kiểm tra câu trả lời AI đã sinh ra, trước khi trả về client.

    Không chạy check_injection_patterns() ở đây - pattern injection là
    đặc trưng của INPUT (người dùng cố ra lệnh cho AI), không có ý
    nghĩa kiểm tra OUTPUT (AI không tự "ra lệnh" cho chính nó). Chỉ
    cần Moderation API để đảm bảo AI không vô tình sinh ra nội dung
    không phù hợp.
    """
    moderation_reason = check_moderation(text)
    if moderation_reason is not None:
        return GuardrailResult(allowed=False, reason=moderation_reason, blocked_by="moderation")

    return GuardrailResult(allowed=True)
