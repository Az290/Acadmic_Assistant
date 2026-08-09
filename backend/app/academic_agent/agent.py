"""
Academic Agent - điều phối 7 bước, nối toàn bộ pipeline đã xây từ các
Tác vụ trước lại thành 1 luồng trả lời câu hỏi hoàn chỉnh.

QUYẾT ĐỊNH KIẾN TRÚC: hàm Python thuần, KHÔNG dùng framework agent
(vd LangGraph). Lý do: luồng xử lý là RẼ NHÁNH CÓ ĐIỀU KIỆN XÁC ĐỊNH
TRƯỚC (nếu Guardrail chặn thì dừng, nếu CHITCHAT thì bỏ qua Retrieval...),
KHÔNG PHẢI vòng lặp AI tự quyết định (không có self-correction, không
có agent tự chọn gọi lại 1 bước nhiều lần không biết trước số lần) -
đây chính là trường hợp framework quản lý state graph không mang lại
lợi ích gì so với if/else thông thường, chỉ thêm độ phức tạp phải học
và debug. Nếu sau này THẬT SỰ cần agent tự lặp (đã có bằng chứng qua
Eval, không phải đoán trước), đó là lúc cân nhắc lại quyết định này.

7 BƯỚC (đã thảo luận và chốt cùng người dùng trước khi code):
1. Guardrail input - chặn thì ghi SecurityLog, KHÔNG lưu Message, dừng.
2. Router classify - biết category + needs_retrieval.
3. Đọc N=10 tin nhắn gần nhất từ Conversation (nếu có).
4. Hybrid Search - chỉ nếu needs_retrieval=True.
5. Sinh câu trả lời - Dynamic Model Routing theo category (prompts.py).
6. Guardrail output - chặn thì trả lỗi fallback ngay, KHÔNG tự thử lại
   (chấp nhận đánh đổi: trải nghiệm kém hơn 1 lần hiếm, đổi lấy không
   tốn thêm 1 lượt gọi LLM cho trường hợp ít xảy ra).
7. Lưu Message (user + assistant) kèm citations, trả về.
"""

import asyncio
import json
from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic_agent.prompts import build_system_prompt, get_model_for_category
from app.config import get_settings
from app.db.models import Conversation, Message, SecurityLog
from app.guardrail.guardrail import check_input, check_output
from app.retrieval.hybrid_search import SearchResult, hybrid_search
from app.router_agent.classifier import classify

# Số tin nhắn gần nhất đọc lại từ lịch sử hội thoại (5 cặp hỏi-đáp) -
# đủ ngữ cảnh cho hội thoại tự nhiên nhiều lượt, không tốn quá nhiều
# token/chi phí cho mỗi lần gọi.
HISTORY_LIMIT = 10

_settings = get_settings()
_client = OpenAI(api_key=_settings.openai_api_key)

FALLBACK_MESSAGE = "Xin lỗi, hệ thống chưa thể tạo câu trả lời phù hợp cho câu hỏi này. Vui lòng thử diễn đạt lại câu hỏi."


@dataclass
class ChatResult:
    conversation_id: int
    answer: str
    category: str
    citations: list[dict] = field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None


async def _log_security_block(
    session: AsyncSession, user_id: int, direction: str, blocked_by: str, reason: str, content: str
) -> None:
    session.add(
        SecurityLog(
            user_id=user_id,
            direction=direction,
            blocked_by=blocked_by,
            reason=reason,
            content=content,
        )
    )
    await session.commit()


async def _get_or_create_conversation(
    session: AsyncSession, conversation_id: int | None, user_id: int, course_id: int | None
) -> Conversation:
    if conversation_id is not None:
        result = await session.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            return conversation
        # conversation_id không tồn tại (vd user gõ nhầm/dữ liệu cũ đã
        # xoá) - tạo phiên MỚI thay vì lỗi cứng, để trải nghiệm không
        # bị gián đoạn chỉ vì 1 id không hợp lệ.

    conversation = Conversation(user_id=user_id, course_id=course_id)
    session.add(conversation)
    await session.flush()
    return conversation


async def _fetch_recent_history(session: AsyncSession, conversation_id: int) -> list[dict]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
    )
    recent_messages = list(reversed(result.scalars().all()))  # đảo lại thành thứ tự CŨ -> MỚI
    return [{"role": m.role, "content": m.content} for m in recent_messages]


def _looks_context_dependent(text: str) -> bool:
    """
    Đoán nhanh 1 câu hỏi có khả năng PHỤ THUỘC ngữ cảnh câu trước hay
    không - dùng để quyết định có đáng tốn 1 lượt gọi LLM viết lại câu
    hỏi hay không. Không cần chính xác tuyệt đối (chỉ là bộ lọc rẻ):
    câu quá ngắn thường là dấu hiệu rõ nhất ("cho ví dụ?", "còn gì
    nữa?", "tại sao?") - câu hỏi tự thân đầy đủ thường dài hơn.
    """
    return len(text.split()) <= 8


def _rewrite_query_with_history(text: str, history: list[dict]) -> str:
    """
    Viết lại câu hỏi NGẮN/PHỤ THUỘC NGỮ CẢNH thành 1 câu ĐỘC LẬP, đầy
    đủ ý nghĩa, dựa trên lịch sử hội thoại gần nhất - PHÁT HIỆN QUA
    TEST THẬT: Hybrid Search tìm theo NGUYÊN VĂN câu hỏi hiện tại,
    không tự hiểu "cho ví dụ cụ thể được không?" đang hỏi về CHỦ ĐỀ gì
    nếu xét riêng lẻ - kết quả tìm kiếm sai hướng, Retrieval trả về
    rỗng dù thực ra tài liệu có đủ thông tin liên quan.

    Kỹ thuật chuẩn trong RAG production (gọi là "query rewriting"/
    "query condensation") - CHỈ chạy khi câu hỏi có dấu hiệu phụ thuộc
    ngữ cảnh (xem _looks_context_dependent), tránh tốn thêm 1 lượt gọi
    LLM cho những câu hỏi đã tự đầy đủ ý nghĩa.
    """
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    response = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Viết lại câu hỏi cuối cùng của user thành 1 câu ĐỘC LẬP, đầy đủ "
                    "ngữ cảnh, dựa trên lịch sử hội thoại. Giữ nguyên ý định gốc, không "
                    "trả lời câu hỏi. Chỉ trả về câu đã viết lại, không giải thích thêm."
                ),
            },
            {"role": "user", "content": f"Lịch sử:\n{history_text}\n\nCâu cần viết lại: {text}"},
        ],
    )
    rewritten = response.choices[0].message.content
    return rewritten.strip() if rewritten else text


def _build_context_text(search_results: list[SearchResult]) -> str:
    if not search_results:
        return "(Không tìm thấy đoạn tài liệu nào liên quan.)"

    blocks = []
    for r in search_results:
        location = f"trang {r.page_number}" if r.page_number else "vị trí không xác định"
        heading = f" - {r.context_prefix}" if r.context_prefix else ""
        blocks.append(f"[Đoạn {r.chunk_id}, {location}{heading}]\n{r.content}")
    return "\n\n".join(blocks)


def _build_citations(search_results: list[SearchResult]) -> list[dict]:
    return [
        {"chunk_id": r.chunk_id, "document_id": r.document_id, "page_number": r.page_number}
        for r in search_results
    ]


async def handle_chat(
    session: AsyncSession,
    *,
    user_id: int,
    message: str,
    conversation_id: int | None = None,
    course_id: int | None = None,
) -> ChatResult:
    """
    Hàm chính - nhận 1 câu hỏi, chạy trọn 7 bước, trả về ChatResult.
    """
    # --- Bước 1: Guardrail input ---
    # check_input là hàm ĐỒNG BỘ (gọi OpenAI qua client sync) - chạy
    # trong thread pool riêng bằng asyncio.to_thread để KHÔNG chặn
    # event loop (các request khác vẫn được xử lý song song trong lúc
    # chờ network I/O của lệnh gọi OpenAI này).
    input_check = await asyncio.to_thread(check_input, message)
    if not input_check.allowed:
        await _log_security_block(
            session, user_id, "input", input_check.blocked_by, input_check.reason, message
        )
        # KHÔNG tạo Conversation mới ở đây nếu client chưa có sẵn 1
        # phiên - câu hỏi đầu tiên bị chặn ngay không nên tạo ra 1
        # phiên hội thoại RỖNG (0 message) trong database, chỉ để
        # trống mãi mãi. Nếu client ĐÃ có conversation_id (đang chat
        # dở), vẫn trả về đúng id đó để họ tiếp tục hỏi câu khác trong
        # cùng phiên - trả về 0 nếu là phiên hoàn toàn mới, client tự
        # hiểu là "chưa có phiên nào được tạo".
        return ChatResult(
            conversation_id=conversation_id or 0,
            answer="Câu hỏi của bạn không hợp lệ, vui lòng đặt câu hỏi khác.",
            category="BLOCKED",
            blocked=True,
            block_reason=input_check.reason,
        )

    conversation = await _get_or_create_conversation(session, conversation_id, user_id, course_id)

    # --- Bước 3 (làm TRƯỚC bước 2 phân loại): đọc lịch sử hội thoại ---
    # Đảo thứ tự so với thiết kế ban đầu - PHÁT HIỆN QUA TEST THẬT:
    # phân loại 1 câu hỏi phụ thuộc ngữ cảnh (vd "cho ví dụ cụ thể
    # được không?") mà KHÔNG có lịch sử trước đó dễ bị hiểu sai (từng
    # bị xếp nhầm SOCRATIC_REQUEST thay vì RAG_QUESTION nối tiếp) - xem
    # chi tiết trong app/router_agent/classifier.py.
    history = await _fetch_recent_history(session, conversation.id)

    # --- Bước 2: Router classify (có kèm ngữ cảnh lịch sử) ---
    route = await asyncio.to_thread(classify, message, history)

    # --- Bước 4: Hybrid Search (chỉ nếu cần) ---
    search_results: list[SearchResult] = []
    if route.needs_retrieval:
        search_query = message
        if history and _looks_context_dependent(message):
            search_query = await asyncio.to_thread(_rewrite_query_with_history, message, history)
        search_results = await hybrid_search(session, query_text=search_query, user_id=user_id)

    # --- Bước 5: Sinh câu trả lời - Dynamic Model Routing ---
    context_text = _build_context_text(search_results)
    system_prompt = build_system_prompt(route.category, context_text)
    model = get_model_for_category(route.category)

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]

    def _call_llm() -> str:
        response = _client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content

    answer = await asyncio.to_thread(_call_llm)

    # --- Bước 6: Guardrail output ---
    output_check = await asyncio.to_thread(check_output, answer)
    if not output_check.allowed:
        await _log_security_block(
            session, user_id, "output", output_check.blocked_by, output_check.reason, answer
        )
        # Đánh đổi CÓ CHỦ Ý, cần biết rõ: câu hỏi user ở lượt này KHÔNG
        # được lưu vào Message (giống input bị chặn) - nếu user hỏi
        # tiếp 1 câu ám chỉ tới câu vừa hỏi ("vậy còn X thì sao"), lịch
        # sử hội thoại sẽ THIẾU ngữ cảnh đó vì hệ thống chưa từng ghi
        # nhận nó. Chấp nhận được vì đây là trường hợp HIẾM (output bị
        # Guardrail chặn không phổ biến) - không lưu 1 cặp hỏi-đáp mà
        # câu trả lời đã bị từ chối tránh làm rối lịch sử chat hiển thị.
        return ChatResult(
            conversation_id=conversation.id,
            answer=FALLBACK_MESSAGE,
            category=route.category,
            blocked=True,
            block_reason=output_check.reason,
        )

    # --- Bước 7: Lưu Message + trả về ---
    citations = _build_citations(search_results)
    session.add(Message(conversation_id=conversation.id, role="user", content=message))
    session.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            citations=json.dumps(citations, ensure_ascii=False) if citations else None,
        )
    )
    await session.commit()

    return ChatResult(
        conversation_id=conversation.id,
        answer=answer,
        category=route.category,
        citations=citations,
    )
