"""
Sinh câu hỏi trắc nghiệm (quiz) cho 1 concept bằng LLM, dựa trên nội
dung tài liệu THẬT đã tra được qua Hybrid Search - KHÔNG để LLM tự bịa
câu hỏi từ "kiến thức chung chung" của nó, giữ đúng nguyên tắc grounding
xuyên suốt dự án (mọi nội dung học thuật phải bám tài liệu đã duyệt).

Câu hỏi sinh ra được LƯU LẠI (cache) ở router.py, không sinh lại mỗi
lần gọi hàm này - xem app/learning/router.py::get_or_create_quiz_question.
"""

import json

from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.retrieval.hybrid_search import hybrid_search

_settings = get_settings()
_client = OpenAI(api_key=_settings.openai_api_key)

QUIZ_MODEL = "gpt-4o-mini"

_QUIZ_SYSTEM_PROMPT = """Bạn là trợ lý tạo câu hỏi trắc nghiệm cho sinh viên, dựa CHỈ trên nội dung tài liệu được cung cấp.

Yêu cầu:
- Tạo ĐÚNG 1 câu hỏi trắc nghiệm, 4 lựa chọn (A/B/C/D), CHỈ 1 đáp án đúng.
- Câu hỏi PHẢI kiểm tra hiểu biết THẬT về khái niệm, không phải câu hỏi mẹo/đánh đố chữ nghĩa.
- Nội dung câu hỏi và các lựa chọn PHẢI dựa trên tài liệu cung cấp - KHÔNG tự bịa thông tin ngoài tài liệu.
- Giải thích ngắn gọn (1-2 câu) tại sao đáp án đó đúng.
- BẮT BUỘC: LUÔN LUÔN viết câu hỏi, 4 phương án trả lời và phần giải thích bằng TIẾNG VIỆT,
  KỂ CẢ KHI đoạn tài liệu tham khảo được cung cấp bằng tiếng Anh - đây là yêu cầu bắt buộc,
  không phải tuỳ chọn. Được phép giữ nguyên thuật ngữ kỹ thuật tiếng Anh trong ngoặc đơn nếu
  cần thiết cho độ chính xác học thuật, ví dụ: "đệ quy (recursion)", "ngăn xếp (stack)".
  TUYỆT ĐỐI KHÔNG trả lời bằng tiếng Anh dưới bất kỳ hình thức nào.

Trả về JSON đúng định dạng (question, options, explanation đều bằng tiếng Việt):
{"question": "...", "options": ["...", "...", "...", "..."], "correct_index": <0-3>, "explanation": "..."}"""


class QuizGenerationError(Exception):
    """Sinh quiz thất bại - có thể do LLM trả JSON không hợp lệ hoặc không đủ tài liệu."""


async def generate_quiz_question(session: AsyncSession, *, concept_name: str, user_id: int) -> dict:
    """
    Tra tài liệu liên quan tới concept_name (dùng lại Hybrid Search có
    sẵn, ACL đã tự áp dụng đúng quyền của user_id), rồi gọi LLM sinh 1
    câu hỏi trắc nghiệm bám nội dung đó.

    Trả về dict với 4 khoá: question, options (list[str] độ dài 4),
    correct_index (0-3), explanation - khớp đúng cột của QuizQuestion.
    """
    search_results = await hybrid_search(session, query_text=concept_name, user_id=user_id, top_k=5)

    if not search_results:
        raise QuizGenerationError(
            f"Không tìm thấy tài liệu nào liên quan tới khái niệm '{concept_name}' để tạo câu hỏi."
        )

    context_text = "\n\n".join(r.content for r in search_results)

    response = _client.chat.completions.create(
        model=QUIZ_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _QUIZ_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Khái niệm: {concept_name}\n\nNội dung tài liệu:\n{context_text}",
            },
        ],
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
        options = parsed["options"]
        correct_index = int(parsed["correct_index"])
        if len(options) != 4 or not (0 <= correct_index <= 3):
            raise ValueError("options phải có đúng 4 phần tử, correct_index phải trong 0-3")
        return {
            "question": parsed["question"],
            "options": options,
            "correct_index": correct_index,
            "explanation": parsed.get("explanation", ""),
        }
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        # LLM đôi khi không tuân thủ đúng schema JSON yêu cầu (hiếm) -
        # không để lỗi này làm sập cả request, báo lỗi rõ ràng để
        # router.py trả về thông báo phù hợp thay vì crash 500 mù mờ.
        raise QuizGenerationError(f"LLM trả về định dạng không hợp lệ: {e}") from e


# ---------------------------------------------------------------------
# Sinh NHIỀU câu hỏi cùng lúc (luồng giảng viên ra đề)
# ---------------------------------------------------------------------

_BATCH_SYSTEM_PROMPT = """Bạn là trợ lý tạo đề trắc nghiệm cho giảng viên đại học, dựa CHỈ trên nội dung tài liệu được cung cấp.

Yêu cầu:
- Tạo ĐÚNG {n} câu hỏi trắc nghiệm KHÁC NHAU, mỗi câu 4 lựa chọn, CHỈ 1 đáp án đúng.
- CỰC KỲ QUAN TRỌNG - {n} câu phải KHÁC BIỆT THẬT SỰ với nhau:
  * KHÔNG được hỏi lại cùng một ý bằng cách diễn đạt khác (vd 3 câu cùng hỏi "cách khai báo list đúng").
  * Mỗi câu phải nhắm vào MỘT KHÍA CẠNH RIÊNG của khái niệm: định nghĩa/cú pháp, cách dùng thực tế,
    phân biệt với khái niệm gần giống, lỗi thường gặp, kết quả khi chạy đoạn mã, trường hợp biên...
  * Trải đều ĐỘ KHÓ: một số câu nhận biết, một số câu vận dụng/phân tích.
- Nội dung câu hỏi và lựa chọn PHẢI bám tài liệu cung cấp - KHÔNG bịa thông tin ngoài tài liệu.
- Mỗi câu kèm giải thích ngắn gọn (1-2 câu) vì sao đáp án đó đúng.
- BẮT BUỘC: viết TOÀN BỘ câu hỏi, lựa chọn và giải thích bằng TIẾNG VIỆT, kể cả khi tài liệu bằng
  tiếng Anh. Được giữ thuật ngữ kỹ thuật tiếng Anh trong ngoặc, vd "đệ quy (recursion)".
  TUYỆT ĐỐI KHÔNG trả lời bằng tiếng Anh.

Trả về JSON đúng định dạng:
{{"questions": [{{"question": "...", "options": ["...","...","...","..."], "correct_index": <0-3>, "explanation": "..."}}]}}"""


def _parse_one_question(item: dict) -> dict:
    """Kiểm tra + chuẩn hoá 1 câu hỏi LLM trả về. Ném ValueError nếu sai schema."""
    options = item["options"]
    correct_index = int(item["correct_index"])
    if len(options) != 4 or not (0 <= correct_index <= 3):
        raise ValueError("options phải có đúng 4 phần tử, correct_index phải trong 0-3")
    return {
        "question": item["question"],
        "options": options,
        "correct_index": correct_index,
        "explanation": item.get("explanation", ""),
    }


async def generate_quiz_questions_batch(
    session: AsyncSession, *, concept_name: str, user_id: int, count: int
) -> list[dict]:
    """
    Sinh `count` câu hỏi trong MỘT lời gọi LLM duy nhất.

    TẠI SAO GỘP 1 LƯỢT thay vì gọi generate_quiz_question() nhiều lần:
    gọi lặp N lần với CÙNG concept_name và CÙNG top-k chunks sẽ cho ra
    N câu gần như trùng nhau (đã gặp thật: 3 câu cùng hỏi "cách khai báo
    list đúng" chỉ khác cách đánh số a/b/c/d) - vì mỗi lượt gọi là độc
    lập, model không biết nó vừa sinh câu gì. Gộp 1 lượt để model NHÌN
    THẤY toàn bộ các câu nó đang tạo, cộng thêm chỉ dẫn tường minh về
    việc phải khác khía cạnh/độ khó, mới thực sự loại được trùng lặp.

    Lấy top_k lớn hơn bản 1 câu (12 thay vì 5): ra đề nhiều câu cần
    nhiều nguyên liệu hơn, nếu chỉ có 5 đoạn thì dù prompt có yêu cầu
    đa dạng, model cũng không có gì khác để hỏi.

    temperature=0.8: có chủ đích CAO hơn mặc định của các lượt gọi khác
    trong dự án (thường 0.0-0.3 để bám tài liệu chặt) - ở đây cần sự đa
    dạng giữa các câu, và độ chính xác nội dung đã được ràng buộc bằng
    grounding (chỉ dùng tài liệu thật) chứ không phải bằng temperature.
    """
    search_results = await hybrid_search(session, query_text=concept_name, user_id=user_id, top_k=12)

    if not search_results:
        raise QuizGenerationError(
            f"Không tìm thấy tài liệu nào liên quan tới khái niệm '{concept_name}' để tạo câu hỏi."
        )

    context_text = "\n\n".join(r.content for r in search_results)

    response = _client.chat.completions.create(
        model=QUIZ_MODEL,
        response_format={"type": "json_object"},
        temperature=0.8,
        messages=[
            {"role": "system", "content": _BATCH_SYSTEM_PROMPT.format(n=count)},
            {
                "role": "user",
                "content": f"Khái niệm: {concept_name}\n\nNội dung tài liệu:\n{context_text}",
            },
        ],
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
        items = parsed["questions"]
        if not isinstance(items, list) or not items:
            raise ValueError("Trường 'questions' phải là danh sách không rỗng")
        return [_parse_one_question(item) for item in items]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        raise QuizGenerationError(f"LLM trả về định dạng không hợp lệ: {e}") from e


async def regenerate_quiz_question(
    session: AsyncSession, *, concept_name: str, user_id: int, current: dict, feedback: str
) -> dict:
    """
    Sinh LẠI 1 câu hỏi theo GÓP Ý của giảng viên (vd "đáp án đúng đang
    sai", "câu này trùng câu 2", "hỏi khó hơn đi").

    Khác generate_quiz_question(): truyền cả câu HIỆN TẠI + góp ý vào
    prompt, để model sửa đúng chỗ được chê thay vì sinh mới hoàn toàn
    từ đầu (giữ được phần giảng viên đã hài lòng).
    """
    search_results = await hybrid_search(session, query_text=concept_name, user_id=user_id, top_k=8)
    if not search_results:
        raise QuizGenerationError(
            f"Không tìm thấy tài liệu nào liên quan tới khái niệm '{concept_name}' để tạo câu hỏi."
        )
    context_text = "\n\n".join(r.content for r in search_results)

    current_text = json.dumps(current, ensure_ascii=False, indent=2)

    response = _client.chat.completions.create(
        model=QUIZ_MODEL,
        response_format={"type": "json_object"},
        temperature=0.5,
        messages=[
            {"role": "system", "content": _QUIZ_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Khái niệm: {concept_name}\n\n"
                    f"Nội dung tài liệu:\n{context_text}\n\n"
                    f"Câu hỏi HIỆN TẠI (do bạn sinh ra trước đó):\n{current_text}\n\n"
                    f"GÓP Ý CỦA GIẢNG VIÊN cần sửa: {feedback}\n\n"
                    "Hãy sinh lại câu hỏi này theo đúng góp ý trên. Giữ nguyên những phần không bị "
                    "chê, chỉ sửa đúng vấn đề giảng viên nêu."
                ),
            },
        ],
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
        return _parse_one_question(parsed)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        raise QuizGenerationError(f"LLM trả về định dạng không hợp lệ: {e}") from e
