"""
Lớp phòng thủ thứ 2: gọi OpenAI Moderation API - MIỄN PHÍ HOÀN TOÀN,
không tính vào chi phí sử dụng thông thường của tài khoản OpenAI.

Vì sao dùng API này thay vì tự viết rule cho nội dung độc hại: phát
hiện nội dung bạo lực/quấy rối/tự hại/nội dung người lớn đòi hỏi hiểu
ngữ nghĩa sâu hơn nhiều so với prompt injection (không chỉ là khớp vài
cụm từ cố định) - đây đúng loại việc rule-based làm kém, còn model
chuyên dụng của OpenAI làm tốt và miễn phí, không có lý do gì tự làm
lại.

GIỚI HẠN QUAN TRỌNG: Moderation API KHÔNG được thiết kế để bắt prompt
injection (đó là việc của rules.py) - nó chỉ phát hiện nội dung có
khả năng gây hại theo các danh mục chuẩn (bạo lực, quấy rối, tự hại,
nội dung người lớn...). Guardrail hoàn chỉnh cần CẢ HAI lớp, không
lớp nào thay thế được lớp kia.
"""

from openai import OpenAI

from app.config import get_settings

MODERATION_MODEL = "omni-moderation-latest"

_settings = get_settings()
_client = OpenAI(api_key=_settings.openai_api_key)


def check_moderation(text: str) -> str | None:
    """
    Gọi Moderation API, trả về chuỗi mô tả lý do nếu nội dung bị gắn
    cờ (flagged), None nếu an toàn.
    """
    response = _client.moderations.create(model=MODERATION_MODEL, input=text)
    result = response.results[0]

    if not result.flagged:
        return None

    flagged_categories = [
        category for category, is_flagged in result.categories.model_dump().items() if is_flagged
    ]
    return f"Nội dung bị gắn cờ bởi OpenAI Moderation: {', '.join(flagged_categories)}"
