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

Trả về JSON đúng định dạng:
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
