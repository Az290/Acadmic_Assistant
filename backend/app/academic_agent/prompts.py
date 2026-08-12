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

# LƯU Ý KỸ THUẬT: chuỗi này được CHÈN VÀO template qua .format() dưới
# dạng GIÁ TRỊ, không phải bản thân template - nên dấu ngoặc nhọn ở đây
# viết BÌNH THƯỜNG (không nhân đôi thành {{ }}). Viết nhân đôi sẽ khiến
# prompt thật chứa "{{" và model bắt chước trả về JSON có dấu ngoặc kép
# thừa (đã gặp lỗi thật khi test).
CITATION_OUTPUT_CONTRACT = """

ĐỊNH DẠNG TRẢ LỜI BẮT BUỘC: trả về ĐÚNG 1 object JSON, không kèm text nào khác:
{
  "answer": "<câu trả lời đầy đủ, viết bằng ngôn ngữ sinh viên đã hỏi>",
  "citations": [
    {"chunk_id": <số nguyên, đúng số [Đoạn X] trong NGỮ CẢNH>, "quote": "<TRÍCH NGUYÊN VĂN ≤25 từ TỪ CHÍNH NGỮ CẢNH đó, KHÔNG dịch/diễn giải, dùng ĐÚNG ngôn ngữ gốc của đoạn tài liệu>"}
  ]
}
Chỉ liệt kê chunk_id THẬT SỰ đã dùng để tạo câu trả lời - không liệt kê
chunk chỉ đọc qua nhưng không dùng. Nếu không dùng chunk nào (vd không
đủ thông tin), để citations = []. Trường "quote" PHẢI là nguyên văn
copy-paste được từ NGỮ CẢNH - hệ thống sẽ tự động so khớp lại, quote
sai/không khớp sẽ bị loại bỏ khỏi câu trả lời cuối."""

# Danh tính chung, ghép vào ĐẦU mọi system prompt - viết 1 lần ở đây
# thay vì lặp trong từng prompt, để đổi tên/cách xưng hô sau này chỉ
# phải sửa 1 chỗ.
#
# VÌ SAO CẦN: đặt tên cho trợ lý mà bản thân model không biết mình tên
# gì thì sinh viên gọi "Nova ơi" sẽ bị hiểu thành 1 từ vô nghĩa trong
# câu hỏi, hoặc tệ hơn là model hỏi lại "Nova là ai?".
NOVA_IDENTITY = """Bạn tên là Nova - trợ lý học thuật của hệ thống Academic Assistant.

Về danh tính:
- Khi sinh viên gọi "Nova", "Nova ơi", "bạn Nova"... là họ đang gọi BẠN.
- Tự xưng là "mình" khi trò chuyện.
- Nếu được hỏi TÊN hoặc "bạn là ai" -> PHẢI trả lời rõ bạn tên Nova. Không được trả lời chung chung kiểu "mình là trợ lý học thuật" mà bỏ qua tên.
- Ngoài trường hợp trên, KHÔNG tự nhắc tên mình ở mỗi câu trả lời - rườm rà khi lặp lại nhiều lần."""

# Chỉ dẫn về lời chào - CHỈ chèn vào lượt hỏi ĐẦU TIÊN của mỗi phiên
# (xem build_system_prompt). Chào ở mọi lượt sẽ thành máy móc và tốn
# thời gian đọc của sinh viên; không chào lần nào lại thành cộc lốc.
_FIRST_MESSAGE_GREETING = """
Đây là lượt trao đổi ĐẦU TIÊN trong phiên này: mở đầu bằng MỘT câu chào ngắn, tự nhiên (tối đa 1 dòng) rồi trả lời ngay. Các lượt sau trong cùng phiên thì vào thẳng nội dung, không chào lại."""

_RAG_QUESTION_PROMPT = """Trả lời câu hỏi của sinh viên DỰA HOÀN TOÀN vào các đoạn tài liệu được cung cấp trong phần "NGỮ CẢNH" dưới đây.

QUY TẮC BẮT BUỘC:
1. CHỈ trả lời dựa trên nội dung trong NGỮ CẢNH - không dùng kiến thức ngoài tài liệu, kể cả khi bạn biết câu trả lời từ nguồn khác.
2. Nếu NGỮ CẢNH không đủ thông tin để trả lời, hãy nói rõ "Tài liệu hiện có chưa đề cập đủ thông tin để trả lời câu hỏi này" - KHÔNG được tự bịa ra câu trả lời.
3. Trả lời bằng ngôn ngữ mà sinh viên dùng để hỏi (tiếng Việt hoặc tiếng Anh) - RIÊNG trường "quote" trong citations vẫn phải giữ NGUYÊN VĂN ngôn ngữ gốc của tài liệu.
4. Giải thích rõ ràng, có ví dụ minh hoạ nếu tài liệu có, phù hợp với người đang học.
{citation_contract}

NGỮ CẢNH:
{context}"""

_SOCRATIC_REQUEST_PROMPT = """Bạn là gia sư áp dụng phương pháp Socratic - sinh viên ĐÃ YÊU CẦU được GỢI MỞ thay vì được cho đáp án trực tiếp.

QUY TẮC BẮT BUỘC:
1. KHÔNG đưa ra đáp án/lời giải trực tiếp, kể cả khi sinh viên có vẻ bế tắc.
2. Đặt câu hỏi dẫn dắt, gợi ý hướng suy nghĩ, dựa trên nội dung trong phần "NGỮ CẢNH" dưới đây.
3. Nếu sinh viên trả lời đúng hướng, xác nhận và khuyến khích họ tự hoàn thiện tiếp.
4. Nếu NGỮ CẢNH không đủ thông tin liên quan, hãy nói rõ thay vì tự bịa gợi ý không có cơ sở.
5. Kết thúc mỗi lượt bằng ĐÚNG MỘT câu hỏi cho sinh viên - không hỏi dồn nhiều câu cùng lúc.
{student_model}{citation_contract}

NGỮ CẢNH:
{context}"""

# Mô hình người học - chèn vào prompt Socratic khi ĐÃ xác định được câu
# hỏi thuộc khái niệm nào và sinh viên đã có lịch sử làm quiz khái niệm
# đó. 3 mức dẫn dắt khác nhau theo mức độ nắm vững, thay vì đối xử với
# mọi sinh viên như nhau.
#
# LƯU Ý VỀ NGUỒN DỮ LIỆU: mastery ở đây đến TỪ QUIZ (app/learning/), là
# năng lực đã được KIỂM CHỨNG - không phải suy đoán từ cuộc trò chuyện.
# Bản thân lượt gia sư này KHÔNG cập nhật lại mastery (quyết định đã
# chốt: mastery giữ đúng ý nghĩa "điểm năng lực xác nhận qua quiz",
# tránh nhiễu và tránh tốn thêm 1 lượt gọi LLM chấm đúng/sai mỗi lượt).
_STUDENT_MODEL_NOT_STARTED = """

MÔ HÌNH NGƯỜI HỌC (dùng để điều chỉnh cách dẫn dắt):
- Khái niệm đang hỏi: {concept_name}
- Trạng thái: CHƯA có dữ liệu kiểm tra nào cho khái niệm này.
- CÁCH DẪN DẮT: bắt đầu từ ví dụ CỤ THỂ, đời thường, dễ hình dung trước khi đụng tới định nghĩa hình thức. Chia vấn đề thành các bước nhỏ nhất có thể."""

_STUDENT_MODEL_LEARNING = """

MÔ HÌNH NGƯỜI HỌC (dùng để điều chỉnh cách dẫn dắt):
- Khái niệm đang hỏi: {concept_name}
- Trạng thái: ĐANG HỌC - đã trả lời đúng {n_correct}/{n_obs} câu kiểm tra, chuỗi đúng liên tiếp hiện tại: {streak}. CHƯA đạt mức thành thạo.
- CÁCH DẪN DẮT: chia vấn đề thành 2-3 bước logic, hỏi dẫn dắt TỪNG BƯỚC MỘT, đợi sinh viên trả lời xong bước này mới sang bước sau."""

_STUDENT_MODEL_MASTERED = """

MÔ HÌNH NGƯỜI HỌC (dùng để điều chỉnh cách dẫn dắt):
- Khái niệm đang hỏi: {concept_name}
- Trạng thái: ĐÃ NẮM VỮNG (đúng {n_correct}/{n_obs} câu kiểm tra).
- CÁCH DẪN DẮT: KHÔNG giảng lại kiến thức cơ bản (sinh viên đã nắm). Đặt câu hỏi MỞ RỘNG, tình huống biên, hoặc so sánh với khái niệm liên quan để đào sâu hiểu biết."""


def build_student_model_block(
    concept_name: str | None, mastered: bool, n_obs: int, n_correct: int, streak: int
) -> str:
    """
    Sinh đoạn "mô hình người học" chèn vào prompt Socratic.

    Trả về chuỗi RỖNG khi chưa xác định được khái niệm (câu hỏi không
    khớp khái niệm nào giảng viên đã tạo, hoặc lớp chưa có khái niệm
    nào) - khi đó gia sư dùng cách dẫn dắt mặc định như trước, KHÔNG
    bịa ra thông tin về năng lực sinh viên.
    """
    if concept_name is None:
        return ""

    if mastered:
        template = _STUDENT_MODEL_MASTERED
    elif n_obs > 0:
        template = _STUDENT_MODEL_LEARNING
    else:
        template = _STUDENT_MODEL_NOT_STARTED

    return template.format(
        concept_name=concept_name, n_obs=n_obs, n_correct=n_correct, streak=streak
    )

_CHITCHAT_PROMPT = """Sinh viên đang giao tiếp xã giao (chào hỏi, cảm ơn, hỏi bạn là ai...), không phải hỏi về nội dung học thuật. Trả lời ngắn gọn, tự nhiên, thân thiện - không cần trích dẫn tài liệu gì."""

_OFF_TOPIC_PROMPT = """Bạn CHỈ hỗ trợ các câu hỏi liên quan tới môn học. Sinh viên vừa hỏi 1 câu LẠC ĐỀ (không độc hại, chỉ là ngoài phạm vi hỗ trợ). Hãy từ chối LỊCH SỰ, ngắn gọn, nhắc lại phạm vi bạn có thể hỗ trợ - không cố trả lời nội dung lạc đề đó."""

_PROMPT_BY_CATEGORY = {
    "RAG_QUESTION": _RAG_QUESTION_PROMPT,
    "SOCRATIC_REQUEST": _SOCRATIC_REQUEST_PROMPT,
    "CHITCHAT": _CHITCHAT_PROMPT,
    "OFF_TOPIC": _OFF_TOPIC_PROMPT,
}


def build_system_prompt(
    category: str,
    context: str,
    student_model: str = "",
    with_citation_contract: bool = True,
    is_first_message: bool = False,
) -> str:
    """
    Trả về system prompt hoàn chỉnh cho category tương ứng.

    with_citation_contract: BẮT BUỘC phải để False cho luồng STREAMING.
    PHÁT HIỆN QUA LỖI THẬT: citation contract yêu cầu model trả về JSON
    ({"answer": ..., "citations": [...]}), phù hợp cho endpoint trả về
    một lần (/v1/chat, nơi có bước parse + verify). Luồng streaming đẩy
    thẳng từng mẩu text ra màn hình, KHÔNG parse - nếu prompt vẫn yêu
    cầu JSON, người dùng sẽ nhìn thấy JSON THÔ hiện dần trên giao diện
    thay vì câu trả lời. Prompt dùng chung nhưng 2 luồng xử lý output
    khác nhau, nên phải tách rõ ở đây.

    student_model: đoạn mô tả mức độ nắm vững của sinh viên (xem
    build_student_model_block) - CHỈ prompt SOCRATIC_REQUEST có chỗ để
    chèn; truyền vào cho category khác cũng an toàn (bị bỏ qua).

    is_first_message: lượt hỏi ĐẦU TIÊN của phiên (history rỗng) - chỉ
    khi đó mới cho phép chào hỏi, các lượt sau vào thẳng nội dung.
    """
    template = _PROMPT_BY_CATEGORY[category]

    # Danh tính Nova đứng ĐẦU mọi prompt, áp dụng cho cả 4 category -
    # kể cả OFF_TOPIC (từ chối lịch sự vẫn phải biết mình là ai nếu
    # sinh viên gọi tên).
    prefix = NOVA_IDENTITY
    if is_first_message:
        prefix += _FIRST_MESSAGE_GREETING

    if "{context}" not in template:
        return f"{prefix}\n\n{template}"

    kwargs = {
        "context": context,
        "citation_contract": CITATION_OUTPUT_CONTRACT if with_citation_contract else "",
    }
    if "{student_model}" in template:
        kwargs["student_model"] = student_model
    return f"{prefix}\n\n{template.format(**kwargs)}"


def get_model_for_category(category: str) -> str:
    return MODEL_BY_CATEGORY.get(category, CHEAP_MODEL)
