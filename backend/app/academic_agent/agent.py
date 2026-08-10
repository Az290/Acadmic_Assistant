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

from app.academic_agent.citation_verifier import verify_citations
from app.academic_agent.prompts import (
    build_student_model_block,
    build_system_prompt,
    get_model_for_category,
)
from app.config import get_settings
from app.db.models import Conversation, Message, SecurityLog
from app.guardrail.guardrail import check_input, check_output
from app.ingestion.embedder import embed_texts
from app.learning.concept_matcher import find_best_concept
from app.learning.student_context import StudentContext, load_student_context
from app.retrieval.hybrid_search import SearchResult, hybrid_search
from app.router_agent.classifier import RouteResult, classify

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
    """
    Dùng RIÊNG cho handle_chat_stream() - trả về TOÀN BỘ chunk đã đưa
    vào context (KHÔNG verify) vì streaming không tương thích với JSON
    output contract cần cho Citation Verification (xem docstring
    _build_verified_citations bên dưới, dùng cho handle_chat() thường).
    """
    return [
        {"chunk_id": r.chunk_id, "document_id": r.document_id, "page_number": r.page_number}
        for r in search_results
    ]


def _infer_course_id(search_results: list[SearchResult]) -> int | None:
    """
    Suy ra Conversation này thuộc lớp nào từ chính các chunk đã tra cứu
    được - lấy course_id XUẤT HIỆN NHIỀU NHẤT trong kết quả tìm kiếm.

    VÌ SAO CẦN: Dashboard giảng viên (app/instructor/) thống kê theo
    Conversation.course_id - nếu cột đó luôn NULL thì mọi số liệu bằng
    0 dù sinh viên hỏi bao nhiêu đi nữa (PHÁT HIỆN QUA TEST THẬT: mọi
    hội thoại trước đó đều có course_id=NULL vì client không gửi kèm).

    GIỚI HẠN CÓ CHỦ Ý: câu CHITCHAT/OFF_TOPIC không tra cứu tài liệu
    nên không suy ra được gì (trả None, Conversation giữ NULL) - chấp
    nhận được vì những câu đó không mang ý nghĩa thống kê học thuật.
    Nếu client CÓ gửi course_id tường minh, giá trị đó được ưu tiên,
    không dùng hàm này.
    """
    if not search_results:
        return None

    counts: dict[int, int] = {}
    for r in search_results:
        counts[r.course_id] = counts.get(r.course_id, 0) + 1
    return max(counts, key=counts.get)


def _parse_llm_response(raw_content: str) -> tuple[str, list[dict]]:
    """
    Parse output của LLM khi đã yêu cầu JSON contract (CITATION_OUTPUT_
    CONTRACT trong prompts.py) - trả về (answer_text, raw_citations).

    raw_citations ở đây CHƯA qua verify (xem citation_verifier.py) và
    CHƯA có document_id/page_number - chỉ có {"chunk_id", "quote"} như
    LLM tự khai.
    """
    try:
        parsed = json.loads(raw_content)
        answer = parsed.get("answer", "")
        raw_citations = parsed.get("citations", [])
        if not answer:
            raise ValueError("Thiếu trường 'answer' trong JSON")
        return answer, raw_citations
    except (json.JSONDecodeError, ValueError, AttributeError):
        # LLM đôi khi không tuân thủ đúng JSON contract (hiếm nhưng có
        # thể xảy ra) - KHÔNG để lỗi này làm sập cả request, coi toàn
        # bộ raw_content là câu trả lời thô, không có citation nào (an
        # toàn hơn là cố gắng "đoán" parse 1 JSON có thể bị hỏng).
        return raw_content, []


def _build_verified_citations(raw_citations: list[dict], search_results: list[SearchResult]) -> list[dict]:
    """
    Citation Verification (Tác vụ #10) - xem docstring đầy đủ trong
    app/academic_agent/citation_verifier.py. Sau khi verify (chỉ giữ
    citation có quote khớp thật với chunk), bổ sung document_id/
    page_number để khớp đúng schema CitationPublic trả về client.
    """
    chunk_contents = {r.chunk_id: r.content for r in search_results}
    chunk_lookup = {r.chunk_id: r for r in search_results}

    verified = verify_citations(raw_citations, chunk_contents)

    result = []
    for c in verified:
        chunk = chunk_lookup.get(c["chunk_id"])
        if chunk is None:
            continue
        result.append(
            {"chunk_id": chunk.chunk_id, "document_id": chunk.document_id, "page_number": chunk.page_number}
        )
    return result


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
    # --- Chuẩn bị lịch sử hội thoại TRƯỚC khi phân loại (không tạo
    # Conversation mới ở bước này) ---
    # Phải có history TRƯỚC bước classify - PHÁT HIỆN QUA TEST THẬT:
    # phân loại 1 câu hỏi phụ thuộc ngữ cảnh (vd "cho ví dụ cụ thể được
    # không?") mà KHÔNG có lịch sử trước đó dễ bị hiểu sai (từng bị xếp
    # nhầm SOCRATIC_REQUEST thay vì RAG_QUESTION nối tiếp) - xem chi
    # tiết trong app/router_agent/classifier.py.
    #
    # CHỦ Ý CHỈ đọc lịch sử khi đã CÓ SẴN conversation_id (phiên đang
    # tiếp diễn) - KHÔNG gọi _get_or_create_conversation() ở đây, để
    # giữ đúng hành vi đã sửa trước đó: câu hỏi ĐẦU TIÊN của 1 phiên
    # HOÀN TOÀN MỚI mà bị Guardrail chặn ngay sẽ KHÔNG tạo ra 1
    # Conversation rỗng trong database. Phiên mới thì chắc chắn chưa
    # có lịch sử nào để tra cứu (history=[] không cần query DB).
    history: list[dict] = []
    if conversation_id is not None:
        history = await _fetch_recent_history(session, conversation_id)

    # --- Bước 1+2 CHẠY SONG SONG: Guardrail input và Router classify ---
    # PHÁT HIỆN QUA ĐO THẬT (không phải đoán): 2 bước này tuần tự tốn
    # ~8s cộng dồn (mỗi bước ~4s, đều là round-trip gọi OpenAI), trong
    # khi CHÚNG KHÔNG PHỤ THUỘC NHAU - cả 2 chỉ cần đúng `message` +
    # `history`, Router không cần biết Guardrail đã cho qua hay chưa để
    # BẮT ĐẦU phân loại. Nếu Guardrail chặn, kết quả classify chỉ đơn
    # giản bị BỎ QUA ở nhánh dưới - lãng phí đúng 1 lượt gọi LLM rẻ cho
    # trường hợp bị chặn (hiếm), đổi lại tiết kiệm ~4s độ trễ NGƯỜI DÙNG
    # THẤY ĐƯỢC ở mọi câu hỏi hợp lệ (đa số) - đánh đổi hợp lý.
    input_check, route = await asyncio.gather(
        asyncio.to_thread(check_input, message),
        asyncio.to_thread(classify, message, history),
    )

    if not input_check.allowed:
        await _log_security_block(
            session, user_id, "input", input_check.blocked_by, input_check.reason, message
        )
        # KHÔNG tạo Conversation mới ở đây nếu client chưa có sẵn 1
        # phiên - câu hỏi đầu tiên bị chặn ngay không nên tạo ra 1
        # phiên hội thoại RỖNG (0 message) trong database. Nếu client
        # ĐÃ có conversation_id (đang chat dở), vẫn trả về đúng id đó.
        return ChatResult(
            conversation_id=conversation_id or 0,
            answer="Câu hỏi của bạn không hợp lệ, vui lòng đặt câu hỏi khác.",
            category="BLOCKED",
            blocked=True,
            block_reason=input_check.reason,
        )

    # Guardrail đã cho qua - giờ mới thật sự cần 1 Conversation để lưu
    # kết quả (tạo mới nếu client chưa có id, hoặc lấy lại đúng phiên
    # cũ - hàm này tự tra history đã đọc ở trên vẫn đúng nếu là phiên
    # cũ, vì conversation.id sẽ khớp với conversation_id đã dùng để
    # đọc history phía trên).
    conversation = await _get_or_create_conversation(session, conversation_id, user_id, course_id)

    # --- Bước 4: Hybrid Search (chỉ nếu cần) ---
    search_results: list[SearchResult] = []
    if route.needs_retrieval:
        search_query = message
        if history and _looks_context_dependent(message):
            search_query = await asyncio.to_thread(_rewrite_query_with_history, message, history)
        search_results = await hybrid_search(session, query_text=search_query, user_id=user_id)

    # Gắn Conversation vào đúng lớp học nếu client chưa chỉ định - phải
    # làm SAU Hybrid Search vì course_id được suy ra từ chính các chunk
    # tra cứu được (xem _infer_course_id). Chỉ gán 1 lần cho mỗi phiên:
    # các lượt hỏi sau trong cùng phiên giữ nguyên lớp đã xác định ở
    # lượt đầu, tránh 1 câu hỏi lạc chủ đề làm đổi lớp của cả hội thoại.
    if conversation.course_id is None:
        inferred_course_id = _infer_course_id(search_results)
        if inferred_course_id is not None:
            conversation.course_id = inferred_course_id

    # --- Bước 5: Sinh câu trả lời - Dynamic Model Routing ---
    context_text = _build_context_text(search_results)
    system_prompt = build_system_prompt(route.category, context_text)
    model = get_model_for_category(route.category)

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]

    # needs_retrieval=True -> prompt đã yêu cầu JSON contract (answer +
    # citations kèm quote) để Citation Verification hoạt động - CHITCHAT/
    # OFF_TOPIC không cần citation, giữ nguyên text thường (không tốn
    # thêm độ phức tạp parse JSON cho câu không cần trích dẫn nào).
    def _call_llm() -> str:
        kwargs = {"model": model, "messages": messages}
        if route.needs_retrieval:
            kwargs["response_format"] = {"type": "json_object"}
        response = _client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    raw_response = await asyncio.to_thread(_call_llm)

    if route.needs_retrieval:
        answer, raw_citations = _parse_llm_response(raw_response)
    else:
        answer, raw_citations = raw_response, []

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
    # Citation Verification (Tác vụ #10) - CHỈ áp dụng ở đây (endpoint
    # không streaming): LLM đã được yêu cầu tự khai citations kèm quote
    # nguyên văn ngay trong response JSON (route.needs_retrieval=True),
    # giờ verify lại quote đó có thật trong chunk hay không. KHÔNG áp
    # dụng ở handle_chat_stream() vì JSON output không stream đẹp từng
    # chữ như text thường (đánh đổi đã thảo luận và chốt cùng người
    # dùng - xem app/academic_agent/citation_verifier.py).
    citations = _build_verified_citations(raw_citations, search_results)

    session.add(Message(conversation_id=conversation.id, role="user", content=message))
    session.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            citations=json.dumps(citations, ensure_ascii=False) if citations else None,
            category=route.category,
            needs_retrieval=route.needs_retrieval,
        )
    )
    await session.commit()

    return ChatResult(
        conversation_id=conversation.id,
        answer=answer,
        category=route.category,
        citations=citations,
    )


async def _run_output_guardrail_in_background(
    session_factory, user_id: int, answer: str
) -> None:
    """
    Chạy Guardrail output SAU KHI đã stream xong cho user xem - KHÔNG
    thể ngăn nội dung đã hiển thị (đã trôi qua rồi), chỉ còn tác dụng
    GHI NHẬN vào SecurityLog để con người xem xét sau nếu phát hiện vi
    phạm. Đây là đánh đổi CÓ CHỦ Ý đã thảo luận: streaming (hiển thị
    ngay từng phần) về bản chất KHÔNG THỂ kết hợp với "phải đọc hết rồi
    mới cho thấy" - chấp nhận rủi ro thấp (system prompt đã giới hạn rõ
    phạm vi học thuật, gpt-4o-mini hiếm khi tự sinh nội dung độc hại)
    để đổi lấy trải nghiệm chat thời gian thực.

    Nhận session_factory (không phải session có sẵn) vì hàm này chạy
    NGOÀI vòng đời của request HTTP gốc (sau khi response đã đóng) -
    session cũ có thể đã bị đóng, cần tự mở phiên DB mới độc lập.
    """
    result = await asyncio.to_thread(check_output, answer)
    if not result.allowed:
        async with session_factory() as session:
            await _log_security_block(session, user_id, "output", result.blocked_by, result.reason, answer)


async def handle_chat_stream(
    session: AsyncSession,
    session_factory,
    *,
    user_id: int,
    message: str,
    conversation_id: int | None = None,
    course_id: int | None = None,
    force_category: str | None = None,
    concept_id: int | None = None,
):
    """
    Biến thể STREAMING của handle_chat() - dùng cho trải nghiệm chat
    thời gian thực (ChatBubble). Khác handle_chat() ở 3 điểm:

    1. KHÔNG đợi Guardrail output trước khi trả về (xem
       _run_output_guardrail_in_background).
    2. Nhận force_category tuỳ chọn ("RAG_QUESTION" hoặc
       "SOCRATIC_REQUEST") - ChatBubble có 2 tab tường minh "Hỏi đáp"/
       "Gia sư", người dùng CHỌN chế độ chứ không để Router tự đoán -
       khi có force_category, BỎ QUA hoàn toàn bước gọi LLM phân loại
       (Router classify), vừa đúng ý người dùng chọn vừa nhanh hơn
       (tiết kiệm đúng 1 lượt gọi OpenAI). Guardrail input VẪN luôn
       chạy dù ép category - không được phép bỏ qua lớp an toàn.
    3. Chế độ gia sư (SOCRATIC_REQUEST) đọc mức độ nắm vững của sinh
       viên để điều chỉnh cách dẫn dắt - xem chú thích ở bước tải
       StudentContext bên dưới.

    concept_id: sinh viên CÓ THỂ chỉ định tường minh mình đang hỏi về
    khái niệm nào (sửa lại nếu hệ thống tự đoán sai); None -> hệ thống
    tự xác định bằng so khớp ngữ nghĩa.
    """
    history: list[dict] = []
    if conversation_id is not None:
        history = await _fetch_recent_history(session, conversation_id)

    # Tải hồ sơ học tập (khái niệm của lớp + mức độ nắm vững) SONG SONG
    # với Guardrail và Router - 3 việc này KHÔNG phụ thuộc kết quả của
    # nhau, chạy nối tiếp là lãng phí thời gian người dùng phải chờ.
    # Chỉ cần cho chế độ gia sư; các chế độ khác bỏ qua để không tốn
    # truy vấn thừa.
    needs_student_context = force_category == "SOCRATIC_REQUEST"

    async def _load_context_if_needed():
        if not needs_student_context:
            return StudentContext()
        return await load_student_context(session, user_id=user_id, course_id=course_id)

    if force_category in ("RAG_QUESTION", "SOCRATIC_REQUEST"):
        input_check, route, student_context = await asyncio.gather(
            asyncio.to_thread(check_input, message),
            asyncio.sleep(0, result=RouteResult(
                category=force_category,
                reasoning="Người dùng chọn tường minh qua tab ChatBubble.",
                needs_retrieval=True,
                classified_by="forced",
            )),
            _load_context_if_needed(),
        )
    else:
        input_check, route, student_context = await asyncio.gather(
            asyncio.to_thread(check_input, message),
            asyncio.to_thread(classify, message, history),
            _load_context_if_needed(),
        )

    if not input_check.allowed:
        await _log_security_block(
            session, user_id, "input", input_check.blocked_by, input_check.reason, message
        )
        yield {"type": "blocked", "conversation_id": conversation_id or 0, "reason": "invalid"}
        return

    conversation = await _get_or_create_conversation(session, conversation_id, user_id, course_id)

    search_results: list[SearchResult] = []
    query_vector: list[float] | None = None
    if route.needs_retrieval:
        search_query = message
        if history and _looks_context_dependent(message):
            search_query = await asyncio.to_thread(_rewrite_query_with_history, message, history)
        # Tính vector câu hỏi 1 LẦN DUY NHẤT rồi dùng cho CẢ 2 việc:
        # tìm tài liệu (Hybrid Search) và xác định khái niệm đang hỏi
        # (concept_matcher) - không gọi API embedding lần thứ hai.
        query_vector = await asyncio.to_thread(lambda: embed_texts([search_query])[0])
        search_results = await hybrid_search(
            session, query_text=search_query, user_id=user_id, query_vector=query_vector
        )

    # Gắn Conversation vào đúng lớp học nếu client chưa chỉ định - xem
    # docstring _infer_course_id (cùng logic với handle_chat()).
    if conversation.course_id is None:
        inferred_course_id = _infer_course_id(search_results)
        if inferred_course_id is not None:
            conversation.course_id = inferred_course_id

    # Chế độ gia sư: xác định câu hỏi thuộc khái niệm nào để đọc mức độ
    # nắm vững của sinh viên. Ưu tiên lựa chọn TƯỜNG MINH của sinh viên
    # (họ sửa lại khi hệ thống đoán sai); không có thì tự đoán bằng so
    # khớp vector - phép tính trong bộ nhớ, không gọi API, ~0ms.
    student_model_block = ""
    matched_concept_id: int | None = None
    if needs_student_context and student_context.concepts:
        if concept_id is not None:
            matched_concept_id = concept_id
            concept_name = next(
                (name for cid, name, _ in student_context.concepts if cid == concept_id), None
            )
        elif query_vector is not None:
            match = find_best_concept(query_vector, student_context.concepts)
            matched_concept_id = match.concept_id if match else None
            concept_name = match.concept_name if match else None
        else:
            concept_name = None

        if matched_concept_id is not None and concept_name is not None:
            m = student_context.mastery_for(matched_concept_id)
            student_model_block = build_student_model_block(
                concept_name=concept_name,
                mastered=m.mastered,
                n_obs=m.n_obs,
                n_correct=m.n_correct,
                streak=m.streak,
            )

    context_text = _build_context_text(search_results)
    # with_citation_contract=False: luồng streaming đẩy thẳng text ra
    # màn hình, không parse JSON - xem docstring build_system_prompt.
    system_prompt = build_system_prompt(
        route.category, context_text, student_model_block, with_citation_contract=False
    )
    model = get_model_for_category(route.category)
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]

    yield {
        "type": "start",
        "conversation_id": conversation.id,
        "category": route.category,
        # Cho Frontend biết hệ thống đã hiểu câu hỏi thuộc khái niệm
        # nào, để sinh viên nhìn thấy và sửa lại nếu đoán sai.
        "concept_id": matched_concept_id,
    }

    # Gọi OpenAI với stream=True - client trả về 1 iterator đồng bộ,
    # phải duyệt nó trong thread riêng (asyncio.to_thread không phù
    # hợp cho generator) - dùng vòng lặp đồng bộ bọc trong 1 thread,
    # đẩy từng mẩu qua asyncio.Queue để generator bất đồng bộ bên
    # ngoài có thể yield ngay khi có dữ liệu mới.
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _stream_worker():
        try:
            stream = _client.chat.completions.create(model=model, messages=messages, stream=True)
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    loop.call_soon_threadsafe(queue.put_nowait, delta)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # tín hiệu kết thúc

    import threading

    threading.Thread(target=_stream_worker, daemon=True).start()

    full_answer_parts: list[str] = []
    while True:
        piece = await queue.get()
        if piece is None:
            break
        full_answer_parts.append(piece)
        yield {"type": "chunk", "text": piece}

    answer = "".join(full_answer_parts)

    citations = _build_citations(search_results)
    session.add(Message(conversation_id=conversation.id, role="user", content=message))
    session.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            citations=json.dumps(citations, ensure_ascii=False) if citations else None,
            category=route.category,
            needs_retrieval=route.needs_retrieval,
        )
    )
    await session.commit()

    yield {"type": "done", "citations": citations}

    # Guardrail output chạy Ở NỀN, KHÔNG chặn response đã stream xong -
    # xem docstring _run_output_guardrail_in_background để hiểu đánh đổi.
    asyncio.create_task(_run_output_guardrail_in_background(session_factory, user_id, answer))
