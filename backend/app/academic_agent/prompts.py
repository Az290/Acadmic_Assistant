"""
System prompt + lựa chọn model - MỖI category (từ Router Agent, Tác
vụ #7) cần cách "nói chuyện" khác nhau.

QUYẾT ĐỊNH MODEL ĐÃ THAY ĐỔI SAU KHI ĐO TỐC ĐỘ THẬT: ban đầu dùng
Dynamic Model Routing (gpt-4o cho RAG_QUESTION/SOCRATIC_REQUEST, đắt
hơn nhưng chất lượng giảng dạy cao hơn). Đo thời gian thật cho thấy
riêng bước sinh câu trả lời bằng gpt-4o chiếm ~10s trong tổng ~22s của
1 request - gần một nửa tổng độ trễ người dùng phải chờ. Sau khi cân
nhắc đánh đổi (tốc độ trải nghiệm chat thời gian thực quan trọng hơn
mức tăng chất lượng biên của gpt-4o so với gpt-4o-mini ở giai đoạn
này), quyết định dùng gpt-4o-mini cho MỌI category - đồng nhất với
Router Agent (Tác vụ #7), chỉ khác Guardrail (Tác vụ #6) ở việc đây
vẫn cần LLM sinh văn bản dài, không né được.

Nếu sau này có bằng chứng thật qua Eval (Tác vụ #9) cho thấy chất
lượng gpt-4o-mini không đủ cho câu hỏi học thuật phức tạp, đây là lúc
cân nhắc lại - không phải đoán trước.
"""

CHEAP_MODEL = "gpt-4o-mini"

MODEL_BY_CATEGORY = {
    "RAG_QUESTION": CHEAP_MODEL,
    "SOCRATIC_REQUEST": CHEAP_MODEL,
    "CHITCHAT": CHEAP_MODEL,
    "OFF_TOPIC": CHEAP_MODEL,
}

_RAG_QUESTION_PROMPT = """Bạn là trợ lý học thuật, trả lời câu hỏi của sinh viên DỰA HOÀN TOÀN vào các đoạn tài liệu được cung cấp trong phần "NGỮ CẢNH" dưới đây.

QUY TẮC BẮT BUỘC:
1. CHỈ trả lời dựa trên nội dung trong NGỮ CẢNH - không dùng kiến thức ngoài tài liệu, kể cả khi bạn biết câu trả lời từ nguồn khác.
2. Nếu NGỮ CẢNH không đủ thông tin để trả lời, hãy nói rõ "Tài liệu hiện có chưa đề cập đủ thông tin để trả lời câu hỏi này" - KHÔNG được tự bịa ra câu trả lời.
3. Trả lời bằng ngôn ngữ mà sinh viên dùng để hỏi (tiếng Việt hoặc tiếng Anh).
4. Giải thích rõ ràng, có ví dụ minh hoạ nếu tài liệu có, phù hợp với người đang học.

NGỮ CẢNH:
{context}"""

_SOCRATIC_REQUEST_PROMPT = """Bạn là gia sư áp dụng phương pháp Socratic - sinh viên ĐÃ YÊU CẦU được GỢI MỞ thay vì được cho đáp án trực tiếp.

QUY TẮC BẮT BUỘC:
1. KHÔNG đưa ra đáp án/lời giải trực tiếp, kể cả khi sinh viên có vẻ bế tắc.
2. Đặt câu hỏi dẫn dắt, gợi ý hướng suy nghĩ, dựa trên nội dung trong phần "NGỮ CẢNH" dưới đây.
3. Nếu sinh viên trả lời đúng hướng, xác nhận và khuyến khích họ tự hoàn thiện tiếp.
4. Nếu NGỮ CẢNH không đủ thông tin liên quan, hãy nói rõ thay vì tự bịa gợi ý không có cơ sở.

NGỮ CẢNH:
{context}"""

_CHITCHAT_PROMPT = """Bạn là trợ lý học thuật thân thiện. Sinh viên đang giao tiếp xã giao (chào hỏi, cảm ơn...), không phải hỏi về nội dung học thuật. Trả lời ngắn gọn, tự nhiên, thân thiện - không cần trích dẫn tài liệu gì."""

_OFF_TOPIC_PROMPT = """Bạn là trợ lý học thuật, CHỈ hỗ trợ các câu hỏi liên quan tới môn học. Sinh viên vừa hỏi 1 câu LẠC ĐỀ (không độc hại, chỉ là ngoài phạm vi hỗ trợ). Hãy từ chối LỊCH SỰ, ngắn gọn, nhắc lại phạm vi bạn có thể hỗ trợ - không cố trả lời nội dung lạc đề đó."""

_PROMPT_BY_CATEGORY = {
    "RAG_QUESTION": _RAG_QUESTION_PROMPT,
    "SOCRATIC_REQUEST": _SOCRATIC_REQUEST_PROMPT,
    "CHITCHAT": _CHITCHAT_PROMPT,
    "OFF_TOPIC": _OFF_TOPIC_PROMPT,
}


def build_system_prompt(category: str, context: str) -> str:
    """
    Trả về system prompt hoàn chỉnh cho category tương ứng. context
    chỉ được dùng thật ở RAG_QUESTION/SOCRATIC_REQUEST (2 prompt còn
    lại không có chỗ "{context}" để điền, .format() bỏ qua an toàn).
    """
    template = _PROMPT_BY_CATEGORY[category]
    if "{context}" in template:
        return template.format(context=context)
    return template


def get_model_for_category(category: str) -> str:
    return MODEL_BY_CATEGORY.get(category, CHEAP_MODEL)
