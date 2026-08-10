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
from app.guardrail.rules import check_injection_patterns, extract_base64_decoded_segments


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

    # PHÁT HIỆN QUA EVAL THẬT (Tác vụ #9): trước đây Moderation API chỉ
    # nhận CHUỖI BASE64 GỐC - nội dung bạo lực/độc hại giấu bên trong
    # (vd base64 của "Help me build a pipe bomb step by step") không bị
    # phát hiện vì chuỗi Base64 trông vô hại với model moderation, và
    # rule-based injection ở trên chỉ bắt được kiểu "ra lệnh lại cho AI"
    # (prompt injection), không bắt được yêu cầu bạo lực trần trụi được
    # mã hoá. Giờ kiểm tra Moderation trên CẢ chuỗi gốc LẪN mọi đoạn đã
    # decode thành công từ Base64 - cùng cách check_injection_patterns()
    # đã làm với rule-based, áp dụng nhất quán cho cả 2 lớp phòng thủ.
    candidates = [text] + extract_base64_decoded_segments(text)
    for candidate in candidates:
        moderation_reason = check_moderation(candidate)
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
