"""
Router Agent - phân loại câu hỏi user vào 1 trong 4 danh mục, quyết
định luồng xử lý phù hợp TRƯỚC KHI tới Academic Agent (Tác vụ #8,
chưa tồn tại - đây là bước chuẩn bị, chưa sinh câu trả lời cuối).

Đây chính là "model routing" đã cố tình HOÃN từ Tác vụ #4.6 (khi đó
chưa có Agent nào tồn tại để mà "route") - giờ có đủ ngữ cảnh để làm
đúng: dùng model RẺ (gpt-4o-mini) chỉ để phân loại, việc sinh câu trả
lời cuối cùng (tốn kém hơn) sẽ dùng model phù hợp tuỳ category, do
Academic Agent quyết định sau này.

4 danh mục:
- RAG_QUESTION: câu hỏi cần tra cứu tài liệu (Hybrid Search) trước khi
  trả lời - loại phổ biến nhất, câu hỏi học thuật thông thường.
- SOCRATIC_REQUEST: user yêu cầu kiểu gia sư gợi mở (không muốn được
  đưa đáp án trực tiếp, muốn được dẫn dắt tự tìm ra) - cần
  prompt/instruction khác hẳn RAG_QUESTION dù cũng cần tra tài liệu.
- CHITCHAT: giao tiếp xã giao (chào hỏi, cảm ơn, tạm biệt) - KHÔNG cần
  tốn 1 lượt Retrieval + Embedding, trả lời thẳng cho nhanh và rẻ.
- OFF_TOPIC: lạc đề nhưng KHÔNG độc hại (Guardrail đã cho qua đúng, vì
  đây không phải nội dung xấu) - Router cần biết để trả lời kiểu "mình
  chỉ hỗ trợ trong phạm vi môn học" thay vì cố trả lời lạc đề.

Chiến lược 2 tầng - RẺ trước, LLM sau (cùng triết lý với Guardrail,
xem app/guardrail/guardrail.py): case rõ ràng (chitchat cực ngắn) xử
lý bằng rule tức thì, không tốn gọi LLM; phần còn lại (đòi hỏi hiểu
NGỮ NGHĨA câu hỏi có thuộc phạm vi học thuật hay không, rule-based
không làm tốt việc này) mới gọi LLM phân loại.
"""

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from app.config import get_settings

CATEGORIES = ["RAG_QUESTION", "SOCRATIC_REQUEST", "CHITCHAT", "OFF_TOPIC"]
CLASSIFIER_MODEL = "gpt-4o-mini"

_settings = get_settings()
_client = OpenAI(api_key=_settings.openai_api_key)

# Câu chitchat cực ngắn, gần như CHẮC CHẮN không cần tra tài liệu -
# liệt kê những mẫu phổ biến nhất, KHÔNG đòi hỏi đầy đủ (phần lớn
# trường hợp mơ hồ hơn sẽ rơi xuống nhánh gọi LLM bên dưới).
_CHITCHAT_PATTERNS = [
    r"^(xin )?chào( bạn)?[!.]?$",
    r"^(cảm ơn|cám ơn)( bạn)?( nhiều)?[!.]?$",
    r"^(tạm biệt|bye)[!.]?$",
    r"^(ok|oke|okay|được)[!.]?$",
    r"^(hi|hello|hey)[!.]?$",
    r"^(thanks|thank you)[!.]?$",
]
_COMPILED_CHITCHAT = [re.compile(p, re.IGNORECASE) for p in _CHITCHAT_PATTERNS]

_CLASSIFIER_SYSTEM_PROMPT = f"""Bạn là bộ phân loại câu hỏi cho hệ thống trợ lý học thuật. Nhiệm vụ DUY NHẤT: xếp câu hỏi của người dùng vào ĐÚNG 1 trong 4 danh mục sau, KHÔNG trả lời câu hỏi:

- RAG_QUESTION: câu hỏi học thuật thông thường, cần tra cứu tài liệu để trả lời (định nghĩa, giải thích khái niệm, cách hoạt động của gì đó...)
- SOCRATIC_REQUEST: người dùng chủ động yêu cầu được HƯỚNG DẪN/GỢI MỞ thay vì được cho đáp án trực tiếp (vd: "đừng cho tôi đáp án, hãy gợi ý thôi", "giúp tôi tự nghĩ ra cách giải")
- CHITCHAT: giao tiếp xã giao, không mang nội dung học thuật (chào hỏi, cảm ơn, hỏi thăm)
- OFF_TOPIC: câu hỏi lạc đề, không liên quan tới học thuật/môn học (nhưng KHÔNG độc hại - nếu độc hại đã bị chặn ở bước khác trước đó)

Trả về JSON đúng định dạng: {{"category": "<một trong 4 giá trị trên>", "reasoning": "<giải thích ngắn gọn 1 câu>"}}"""


@dataclass
class RouteResult:
    category: str
    reasoning: str
    needs_retrieval: bool  # RAG_QUESTION và SOCRATIC_REQUEST đều cần tra tài liệu
    classified_by: str  # "rules" hoặc "llm" - phục vụ debug/log, biết tầng nào quyết định


def _check_chitchat_rules(text: str) -> bool:
    stripped = text.strip()
    return any(pattern.match(stripped) for pattern in _COMPILED_CHITCHAT)


def classify(text: str, history: list[dict] | None = None) -> RouteResult:
    """
    Phân loại 1 câu hỏi/tin nhắn. Rule-based trước (rẻ, tức thì) - chỉ
    gọi LLM nếu không khớp chitchat rõ ràng.

    history: vài lượt hỏi-đáp GẦN NHẤT (tuỳ chọn) - QUAN TRỌNG cho hội
    thoại nhiều lượt, vì 1 câu như "cho ví dụ cụ thể được không?" hoàn
    toàn MƠ HỒ nếu xét ĐƠN LẺ (có thể là SOCRATIC_REQUEST kiểu "gợi ý
    thêm"), nhưng rõ ràng là RAG_QUESTION nối tiếp nếu biết câu hỏi
    ngay trước đó đang hỏi về 1 khái niệm cụ thể. Không truyền history
    vẫn hoạt động được (dùng ở endpoint test độc lập /v1/route/classify,
    nơi không có ngữ cảnh hội thoại) - chỉ kém chính xác hơn với câu
    hỏi phụ thuộc ngữ cảnh trước đó.
    """
    if _check_chitchat_rules(text):
        return RouteResult(
            category="CHITCHAT",
            reasoning="Khớp mẫu câu chào hỏi/xã giao ngắn, không cần gọi LLM phân loại.",
            needs_retrieval=False,
            classified_by="rules",
        )

    messages = [{"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT}]
    if history:
        # Chỉ đưa vài lượt gần nhất làm NGỮ CẢNH tham khảo, không yêu
        # cầu phân loại chúng - giữ nguyên "user" là câu CẦN phân loại,
        # đặt cuối cùng để LLM hiểu rõ đâu là câu cần xếp loại.
        messages.append(
            {
                "role": "system",
                "content": "Lịch sử hội thoại gần đây (chỉ để tham khảo ngữ cảnh, KHÔNG phân loại các câu này):\n"
                + "\n".join(f"{m['role']}: {m['content']}" for m in history),
            }
        )
    messages.append({"role": "user", "content": text})

    response = _client.chat.completions.create(
        model=CLASSIFIER_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
    )
    raw_content = response.choices[0].message.content

    try:
        parsed = json.loads(raw_content)
        category = parsed.get("category", "")
        reasoning = parsed.get("reasoning", "")
    except (json.JSONDecodeError, AttributeError):
        # LLM đôi khi không tuân thủ JSON mode hoàn hảo (hiếm nhưng có
        # thể xảy ra) - không để lỗi này làm sập cả request, coi như
        # RAG_QUESTION (an toàn nhất: vẫn tra tài liệu trước khi trả
        # lời, không bỏ sót ngữ cảnh cần thiết).
        category = "RAG_QUESTION"
        reasoning = "Không phân loại được phản hồi từ LLM (lỗi định dạng) - mặc định coi là câu hỏi cần tra tài liệu để an toàn."

    if category not in CATEGORIES:
        category = "RAG_QUESTION"
        reasoning = f"LLM trả về danh mục không hợp lệ ('{category}') - mặc định RAG_QUESTION."

    return RouteResult(
        category=category,
        reasoning=reasoning,
        needs_retrieval=category in ("RAG_QUESTION", "SOCRATIC_REQUEST"),
        classified_by="llm",
    )
