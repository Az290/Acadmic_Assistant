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
import re
import time
from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic_agent.citation_verifier import verify_citations
from app.academic_agent.evidence_planner import PlannerResult, plan_evidence
from app.academic_agent.prompts import (
    DEADLINE_ALERT_HEADING,
    build_deadline_alert_block,
    build_learning_progress_block,
    build_recent_mistake_block,
    build_student_model_block,
    build_system_prompt,
    get_model_for_category,
    get_temperature_for_category,
)
from app.academic_agent.role_policy import RoleContext, resolve_role_context
from app.academic_agent.instructor_context import build_instructor_context_block, load_instructor_context
from app.academic_agent.response_composer import (
    build_plan_instruction,
    compose_grounded_response,
    normalize_socratic_answer,
    planned_citation_ids,
)
from app.academic_agent.schemas import ActionResultPublic, PendingActionPublic
from app.academic_agent.system_kb_service import SystemKBQuerier
from app.academic_agent.tool_executor import ToolExecutionResult, execute_tool
from app.academic_agent.tools import TOOL_LABELS_VI, TOOLS_REQUIRING_CONFIRMATION, get_tools_for_role
from app.config import get_settings
from app.db.models import AppUser, Conversation, Message, SecurityLog
from app.guardrail.guardrail import check_input, check_output
from app.ingestion.embedder import embed_texts
from app.internal_learning.service import search_modules
from app.learning.concept_matcher import find_best_concept
from app.learning.student_context import StudentContext, load_student_context
from app.personalization.context_builder import (
    build_personalization_context,
    build_personalization_instruction,
)
from app.operations.rollout import is_user_in_rollout
from app.personalization.service import get_preference
from app.personalization.memory_service import (
    build_memory_instruction,
    load_conversation_memory,
    refresh_conversation_memory,
)
from app.retrieval.hybrid_search import SearchResult, hybrid_search
from app.router_agent.classifier import RouteResult, classify

# Số tin nhắn gần nhất đọc lại từ lịch sử hội thoại (5 cặp hỏi-đáp) -
# đủ ngữ cảnh cho hội thoại tự nhiên nhiều lượt, không tốn quá nhiều
# token/chi phí cho mỗi lần gọi.
HISTORY_LIMIT = 10

_settings = get_settings()
_client = OpenAI(api_key=_settings.openai_api_key)


def _answer_owner_learning_question(message: str, history: list[dict]) -> str:
    """Nhánh RAG nội bộ riêng; chỉ caller đã xác thực role OWNER mới được gọi."""
    evidence_text = json.dumps(search_modules(message, limit=3), ensure_ascii=False)
    response = _client.chat.completions.create(
        model=get_model_for_category("RAG_QUESTION"),
        temperature=0.25,
        messages=[
            {
                "role": "system",
                "content": (
                    "Bạn là Nova trong chế độ cố vấn kỹ thuật riêng cho chủ hệ thống Academic Assistant. "
                    "Giải thích bằng đúng ngôn ngữ người dùng, tự nhiên và có ví dụ từ dự án. "
                    "Chỉ khẳng định chi tiết kiến trúc nội bộ khi được EVIDENCE hỗ trợ; nếu kho bài học chưa có "
                    "thì nói rõ giới hạn. Không tiết lộ secret, token, mật khẩu hay dữ liệu người dùng."
                ),
            },
            {"role": "system", "content": f"EVIDENCE TỪ KHÓA HỌC NỘI BỘ:\n{evidence_text}"},
            *history[-6:],
            {"role": "user", "content": message},
        ],
    )
    return response.choices[0].message.content or "Mình chưa có đủ nội dung nội bộ để giải thích phần này."

NO_ENROLLMENT_MESSAGE = (
    "Bạn chưa tham gia lớp học nào nên mình chưa có tài liệu nào để tra cứu. "
    "Hãy liên hệ giảng viên để được thêm vào lớp bằng chính email tài khoản của bạn. "
    "Sau khi vào lớp, mình có thể trả lời câu hỏi dựa trên tài liệu của lớp đó."
)

FALLBACK_MESSAGE = "Xin lỗi, hệ thống chưa thể tạo câu trả lời phù hợp cho câu hỏi này. Vui lòng thử diễn đạt lại câu hỏi."


@dataclass
class ChatResult:
    conversation_id: int
    answer: str
    category: str
    citations: list[dict] = field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None
    # CHỈ có giá trị khi category="ACTION_REQUEST" - xem docstring
    # PendingActionPublic/ActionResultPublic (schemas.py) và
    # _handle_action_request() bên dưới.
    pending_action: PendingActionPublic | None = None
    action_result: ActionResultPublic | None = None


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
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
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


async def _fetch_recent_history(
    session: AsyncSession, conversation_id: int, user_id: int
) -> list[dict]:
    result = await session.execute(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.conversation_id == conversation_id)
        .where(Conversation.user_id == user_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
    )
    recent_messages = list(reversed(result.scalars().all()))  # đảo lại thành thứ tự CŨ -> MỚI
    return [{"role": m.role, "content": m.content} for m in recent_messages]


async def _conversation_has_deadline_alert(
    session: AsyncSession, conversation_id: int | None, user_id: int
) -> bool:
    if conversation_id is None:
        return False
    found = (
        await session.execute(
            select(Message.id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.conversation_id == conversation_id,
                Conversation.user_id == user_id,
                Message.role == "assistant",
                Message.content.contains(DEADLINE_ALERT_HEADING),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def _resolve_active_course_id(
    session: AsyncSession,
    *,
    conversation_id: int | None,
    user_id: int,
    requested_course_id: int | None,
) -> int | None:
    """Conversation đã có lớp thì giữ nguyên; không tin ID phiên của user khác."""
    if conversation_id is None:
        return requested_course_id
    stored_course_id = (
        await session.execute(
            select(Conversation.course_id).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    return stored_course_id if stored_course_id is not None else requested_course_id


# ============================================================
# ACTION_REQUEST - function-calling cho phép Nova THỰC HIỆN hành động
# thay vì chỉ trả lời câu hỏi (xem app/academic_agent/tools.py +
# tool_executor.py). Helper dùng CHUNG giữa handle_chat() và
# handle_chat_stream() được gom vào đây - cùng nguyên tắc đã áp dụng
# cho _get_or_create_conversation/_fetch_recent_history phía trên,
# tránh copy-paste logic 2 lần cho 2 hàm.
# ============================================================

ACTION_TOOL_MODEL = "gpt-4o-mini"

# Rule-based trước (rẻ, tức thì) cho ý định xác nhận/huỷ - CÙNG triết
# lý 2 tầng đã dùng ở router_agent/classifier.py::_check_chitchat_rules:
# case rõ ràng xử lý bằng regex, chỉ câu mơ hồ mới tốn 1 lượt gọi LLM.
_CONFIRM_PATTERNS = [
    r"^(có|đồng ý|ok|oke|okay|được|làm đi|xác nhận|yes|yep|ừ|ừm|uh)[!.,]?$",
]
_CANCEL_PATTERNS = [
    r"^(không|thôi|huỷ|hủy|đừng|cancel|no|nope)[!.,]?$",
]
_COMPILED_CONFIRM = [re.compile(p, re.IGNORECASE) for p in _CONFIRM_PATTERNS]
_COMPILED_CANCEL = [re.compile(p, re.IGNORECASE) for p in _CANCEL_PATTERNS]


def _check_confirmation_rules(text: str) -> bool | None:
    """
    True = xác nhận, False = huỷ, None = không khớp rule rõ ràng nào
    (câu dài/mơ hồ) - lúc đó gọi tiếp _classify_confirmation_with_llm().
    """
    stripped = text.strip()
    if any(p.match(stripped) for p in _COMPILED_CONFIRM):
        return True
    if any(p.match(stripped) for p in _COMPILED_CANCEL):
        return False
    return None


def _classify_confirmation_with_llm(text: str, pending_summary: str) -> tuple[bool, bool]:
    """
    Trả về (is_confirmation, confirmed). is_confirmation=False nghĩa là
    câu này KHÔNG phải lời xác nhận/từ chối cho hành động đang chờ, mà
    là 1 câu hỏi/yêu cầu MỚI khác - lúc đó confirmed vô nghĩa (luôn
    False), pending_action cũ coi như tự động hết hạn/bị thay thế (xem
    logic gọi hàm này trong _handle_action_request_turn()).

    Dùng model RẺ (gpt-4o-mini), KHÔNG tools, response_format json_object
    - đây chỉ là bước phân loại Ý ĐỊNH ngắn, không cần model mạnh.
    """
    try:
        response = _client.chat.completions.create(
            model=ACTION_TOOL_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Hệ thống đang có 1 hành động CHỜ người dùng xác nhận: "
                        f"\"{pending_summary}\". Xét câu trả lời mới nhất của người dùng: "
                        "đây có phải lời XÁC NHẬN (đồng ý thực hiện) hay TỪ CHỐI (huỷ) hành "
                        "động đó, hay là một câu hỏi/yêu cầu HOÀN TOÀN KHÁC (không liên quan "
                        "tới việc xác nhận/huỷ)? Trả về JSON: "
                        '{"is_confirmation": <true nếu là xác nhận/từ chối, false nếu là câu khác>, '
                        '"confirmed": <true nếu đồng ý, false nếu từ chối - chỉ có ý nghĩa khi is_confirmation=true>}'
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        parsed = json.loads(response.choices[0].message.content)
        return bool(parsed.get("is_confirmation", False)), bool(parsed.get("confirmed", False))
    except Exception:
        # Lỗi bất kỳ (mạng, JSON hỏng...) -> AN TOÀN hơn là coi như KHÔNG
        # phải xác nhận, để rơi xuống xử lý như 1 ACTION_REQUEST mới -
        # tránh trường hợp tệ hơn: hiểu nhầm 1 câu hỏi khác thành "đồng
        # ý" rồi lỡ thực thi hành động người dùng không thật sự muốn.
        return False, False


def _build_arguments_summary(tool_name: str, arguments: dict) -> str:
    """
    Text tiếng Việt NGƯỜI ĐỌC ĐƯỢC mô tả tham số của 1 tool - dùng cho
    PendingActionPublic.arguments_summary, KHÔNG hiện JSON thô cho
    người dùng (xem docstring PendingActionPublic).
    """
    parts = [f"{key}: {value}" for key, value in arguments.items()]
    return f"{TOOL_LABELS_VI.get(tool_name, tool_name)} ({', '.join(parts)})" if parts else TOOL_LABELS_VI.get(
        tool_name, tool_name
    )


def _summarize_tool_result_with_llm(user_question: str, data: dict) -> str:
    """
    "Kể lại" kết quả 1 tool ĐỌC thành câu văn tự nhiên tiếng Việt, thay
    vì hiện JSON thô cho người dùng - dùng model RẺ, KHÔNG tools, prompt
    ngắn. Lỗi bất kỳ -> fallback về chuỗi JSON thô (an toàn hơn là làm
    sập cả lượt trả lời chỉ vì bước "văn vẻ hoá" phụ này gặp sự cố).
    """
    try:
        response = _client.chat.completions.create(
            model=ACTION_TOOL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Dựa vào dữ liệu JSON sau, trả lời câu hỏi của người dùng bằng tiếng "
                        "Việt tự nhiên, ngắn gọn, dễ hiểu - KHÔNG hiện lại JSON thô, không bịa "
                        "thêm thông tin ngoài dữ liệu đã cho."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Câu hỏi: {user_question}\n\nDữ liệu:\n{json.dumps(data, ensure_ascii=False)}",
                },
            ],
        )
        content = response.choices[0].message.content
        return content.strip() if content else json.dumps(data, ensure_ascii=False)
    except Exception:
        return json.dumps(data, ensure_ascii=False)


async def _fetch_last_pending_action(session: AsyncSession, conversation_id: int) -> tuple[int, dict] | None:
    """
    Tin nhắn ASSISTANT CUỐI CÙNG của conversation này có pending_action
    đang chờ không - trả về (message_id, parsed_pending_action) hoặc
    None. CHỈ xét tin nhắn CUỐI CÙNG (không phải "bất kỳ pending_action
    nào trong lịch sử") - đúng thiết kế cột Message.pending_action: chỉ
    có ý nghĩa nếu là tin nhắn MỚI NHẤT (xem docstring cột trong
    db/models.py).
    """
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_assistant_message = result.scalar_one_or_none()
    if last_assistant_message is None or not last_assistant_message.pending_action:
        return None

    try:
        parsed = json.loads(last_assistant_message.pending_action)
    except (json.JSONDecodeError, TypeError):
        return None
    return last_assistant_message.id, parsed


@dataclass
class ActionRequestOutcome:
    """
    Kết quả của 1 lượt xử lý ACTION_REQUEST - đủ thông tin để CẢ 2 hàm
    (handle_chat/handle_chat_stream) tự build response/SSE event theo
    đúng định dạng riêng của mình, không phải parse lại text.
    """

    answer_text: str
    pending_action: PendingActionPublic | None
    action_result: ActionResultPublic | None
    pending_action_json: str | None  # để lưu vào cột Message.pending_action, None nếu không có


async def _handle_action_request_turn(
    session: AsyncSession,
    *,
    conversation_id: int,
    user: AppUser,
    message: str,
    role_context: RoleContext,
) -> ActionRequestOutcome:
    """
    LÕI xử lý 1 lượt ACTION_REQUEST - dùng chung cho cả handle_chat() và
    handle_chat_stream(). KHÔNG lưu Message ở đây (2 hàm gọi có cách lưu
    khác nhau đôi chút, vd handle_chat_stream cần message_id để yield) -
    chỉ trả về ActionRequestOutcome, người gọi tự lưu Message.

    Luồng (đã mô tả chi tiết trong kế hoạch, tóm tắt lại đây):
    1. Có pending_action từ tin nhắn assistant cuối cùng?
       a. CÓ -> câu hiện tại có phải xác nhận/huỷ? (rule trước, LLM sau)
          - Xác nhận -> execute_tool() -> trả kết quả.
          - Huỷ -> trả lời đã huỷ.
          - Không phải (câu mới khác) -> rơi xuống bước 2, pending cũ
            coi như hết hiệu lực (KHÔNG set lại pending_action cũ).
       b. KHÔNG -> bước 2.
    2. Gọi LLM với tools=get_tools_for_role(), tool_choice="auto".
       - Có tool_call (tool GHI) -> đề xuất, chờ xác nhận.
       - Có tool_call (tool ĐỌC) -> thực thi ngay, kể lại kết quả.
       - Không tool_call -> trả lời text thường.
    """
    pending = await _fetch_last_pending_action(session, conversation_id)

    if pending is not None:
        _, pending_data = pending
        tool_name = pending_data.get("tool_name", "")
        arguments = pending_data.get("arguments", {})
        pending_summary = _build_arguments_summary(tool_name, arguments)

        confirmed = _check_confirmation_rules(message)
        is_confirmation = confirmed is not None
        if not is_confirmation:
            is_confirmation, confirmed = await asyncio.to_thread(
                _classify_confirmation_with_llm, message, pending_summary
            )

        if is_confirmation:
            if confirmed:
                result = await execute_tool(
                    session,
                    tool_name=tool_name,
                    arguments=arguments,
                    user=user,
                    conversation_id=conversation_id,
                )
                label = TOOL_LABELS_VI.get(tool_name, tool_name)
                if result.success:
                    answer = f"Mình đã thực hiện xong: {label.lower()}."
                    if result.data:
                        answer += f" Kết quả: {json.dumps(result.data, ensure_ascii=False)}"
                else:
                    answer = f"Rất tiếc, mình không thực hiện được: {result.error_message}"
                return ActionRequestOutcome(
                    answer_text=answer,
                    pending_action=None,
                    action_result=ActionResultPublic(
                        tool_name=tool_name, tool_label_vi=label, success=result.success,
                        summary=result.error_message if not result.success else answer,
                    ),
                    pending_action_json=None,
                )
            else:
                label = TOOL_LABELS_VI.get(tool_name, tool_name)
                answer = f"Đã huỷ. Mình sẽ không thực hiện: {label.lower()}."
                return ActionRequestOutcome(
                    answer_text=answer,
                    pending_action=None,
                    action_result=ActionResultPublic(
                        tool_name=tool_name, tool_label_vi=label, success=False, summary="Người dùng đã huỷ hành động."
                    ),
                    pending_action_json=None,
                )
        # is_confirmation=False -> rơi xuống xử lý như ACTION_REQUEST
        # mới bên dưới, pending cũ tự động hết hiệu lực (không set lại).

    # --- Không có pending_action (hoặc vừa hết hiệu lực) - gọi LLM tool-calling ---
    tools = get_tools_for_role(role_context.effective_role)
    if not tools:
        return ActionRequestOutcome(
            answer_text="Xin lỗi, tài khoản của bạn hiện chưa được hỗ trợ thực hiện hành động qua chat.",
            pending_action=None,
            action_result=None,
            pending_action_json=None,
        )

    def _call_llm_with_tools():
        return _client.chat.completions.create(
            model=ACTION_TOOL_MODEL,
            tools=tools,
            tool_choice="auto",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là Nova, trợ lý học thuật. Người dùng vừa yêu cầu 1 hành động "
                        "hoặc muốn xem thông tin quản trị/tiến độ cụ thể. Nếu có tool phù hợp, "
                        f"Vai trò hiệu lực hiện tại là {role_context.effective_role}; "
                        f"lớp đang hoạt động là {role_context.course_id}. "
                        "hãy gọi ĐÚNG 1 tool với tham số chính xác nhất suy luận được từ câu hỏi. "
                        "Nếu KHÔNG có tool nào phù hợp, hãy trả lời trực tiếp bằng tiếng Việt, "
                        "ngắn gọn - đừng cố gọi tool không liên quan."
                    ),
                },
                {"role": "user", "content": message},
            ],
        )

    response = await asyncio.to_thread(_call_llm_with_tools)
    choice_message = response.choices[0].message

    if not choice_message.tool_calls:
        answer = choice_message.content or "Xin lỗi, mình chưa hiểu rõ yêu cầu này."
        return ActionRequestOutcome(
            answer_text=answer, pending_action=None, action_result=None, pending_action_json=None
        )

    # CHỈ xử lý tool_call ĐẦU TIÊN - đúng triết lý "if/else xác định
    # trước", KHÔNG lặp gọi nhiều tool trong 1 lượt (xem docstring đầu file).
    tool_call = choice_message.tool_calls[0]
    tool_name = tool_call.function.name
    try:
        arguments = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        return ActionRequestOutcome(
            answer_text="Xin lỗi, mình không xác định được chính xác tham số cho yêu cầu này. Bạn có thể nói rõ hơn không?",
            pending_action=None,
            action_result=None,
            pending_action_json=None,
        )

    if tool_name in TOOLS_REQUIRING_CONFIRMATION:
        label = TOOL_LABELS_VI.get(tool_name, tool_name)
        arguments_summary = _build_arguments_summary(tool_name, arguments)
        answer = f"Bạn có muốn mình thực hiện: {arguments_summary} không? Trả lời \"có\" để xác nhận hoặc \"không\" để huỷ."
        return ActionRequestOutcome(
            answer_text=answer,
            pending_action=PendingActionPublic(
                tool_name=tool_name, tool_label_vi=label, arguments_summary=arguments_summary
            ),
            action_result=None,
            pending_action_json=json.dumps({"tool_name": tool_name, "arguments": arguments}, ensure_ascii=False),
        )

    # Tool ĐỌC - thực thi ngay, không cần xác nhận.
    result = await execute_tool(
        session, tool_name=tool_name, arguments=arguments, user=user, conversation_id=conversation_id
    )
    label = TOOL_LABELS_VI.get(tool_name, tool_name)
    if result.success:
        if tool_name == "draft_assignment_reminder":
            data = result.data or {}
            recipients = data.get("intended_recipients", [])
            answer = (
                "Đây chỉ là bản nháp, Nova chưa gửi thông báo cho bất kỳ ai.\n\n"
                f"Đối tượng dự kiến: {len(recipients)} sinh viên chưa nộp bài.\n"
                f"Lý do: {data.get('reason', 'Chưa ghi nhận bài nộp')}.\n\n"
                f"{data.get('draft_content', '')}"
            )
        else:
            answer = await asyncio.to_thread(
                _summarize_tool_result_with_llm, message, result.data or {}
            )
    else:
        answer = f"Rất tiếc, mình không lấy được thông tin này: {result.error_message}"

    return ActionRequestOutcome(
        answer_text=answer,
        pending_action=None,
        action_result=ActionResultPublic(
            tool_name=tool_name, tool_label_vi=label, success=result.success,
            summary=result.error_message if not result.success else answer,
        ),
        pending_action_json=None,
    )


def _looks_context_dependent(text: str) -> bool:
    """
    Đoán nhanh 1 câu hỏi có khả năng PHỤ THUỘC ngữ cảnh câu trước hay
    không - dùng để quyết định có đáng tốn 1 lượt gọi LLM viết lại câu
    hỏi hay không. Không cần chính xác tuyệt đối (chỉ là bộ lọc rẻ):
    câu quá ngắn thường là dấu hiệu rõ nhất ("cho ví dụ?", "còn gì
    nữa?", "tại sao?") - câu hỏi tự thân đầy đủ thường dài hơn.
    """
    return len(text.split()) <= 8


# Regex khớp bất kỳ ký tự có dấu tiếng Việt nào (nguyên âm có dấu + đ/Đ) -
# ĐÚNG regex đã dùng khi ĐO THẬT trên traffic sản xuất (xem kết quả đo ở
# đầu file/PR liên quan): nếu câu KHÔNG chứa ký tự nào trong tập này, đó
# là dấu hiệu mạnh cho thấy câu tiếng Việt đã bị gõ THIẾU DẤU (không phải
# bằng chứng chắc chắn - câu tiếng Anh cũng không có ký tự này).
_VIETNAMESE_ACCENT_CHARS = (
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    r"ùúụủũưừứựửữỳýỵỷỹđ]"
)
_VIETNAMESE_ACCENT_RE = re.compile(_VIETNAMESE_ACCENT_CHARS, re.IGNORECASE)

# Tập từ tiếng Việt phổ biến khi bị gõ KHÔNG DẤU - ĐÚNG tập đã dùng khi ĐO
# THẬT (~31% traffic là tiếng Việt không dấu). Đây là heuristic RẺ, không
# cần chính xác tuyệt đối - cùng triết lý với _looks_context_dependent:
# chỉ cần đủ tin cậy để quyết định có đáng tốn 1 lượt gọi LLM khôi phục
# dấu hay không, không cần bắt đúng 100% mọi câu.
_UNACCENTED_VIETNAMESE_WORDS = {
    "la", "gi", "trong", "va", "cua", "duoc", "khong", "the", "nao",
    "hoat", "dong", "cach", "cai", "dat", "nhu", "the", "nay", "de",
    "quy", "ham", "bien", "voi", "cho", "tai", "sao", "neu", "thi",
    "mot", "hai", "ba", "cac", "nhung", "co", "phai", "lam", "sinh",
}


def _looks_like_unaccented_vietnamese(text: str) -> bool:
    """
    Đoán nhanh câu có khả năng là tiếng Việt bị gõ THIẾU DẤU - ĐO ĐƯỢC
    QUA TEST THẬT: câu đúng chủ đề bị GIẢM điểm tương đồng khi mất dấu
    ("đệ quy" 0.478 -> "de quy" 0.334), trong khi câu lạc đề lại bị TĂNG
    điểm ("Docker" 0.276 -> 0.309) - 2 nhóm chồng lấn nhau (gap -0.017),
    KHÔNG ngưỡng similarity nào tách được. Case thật: "Ham de quy hoat
    dong nhu the nao?" trả về 0 kết quả tìm kiếm dù tài liệu có đủ nội
    dung liên quan.

    Logic (heuristic RẺ, không cần chính xác tuyệt đối - cùng tinh thần
    với _looks_context_dependent): câu KHÔNG có bất kỳ ký tự có dấu tiếng
    Việt nào, VÀ chứa ít nhất 2 từ trong tập từ tiếng Việt phổ biến không
    dấu. Điều kiện "ít nhất 2 từ" để loại câu tiếng Anh thuần (vd "What
    is a Python list?" không match dù không có dấu) và loại câu 1 từ
    không đủ tín hiệu (vd "Python").
    """
    if _VIETNAMESE_ACCENT_RE.search(text):
        # Đã có dấu rồi -> không cần khôi phục.
        return False

    words = re.findall(r"[a-zA-Z]+", text.lower())
    matches = sum(1 for w in words if w in _UNACCENTED_VIETNAMESE_WORDS)
    return matches >= 2


def _restore_vietnamese_accents(text: str) -> str:
    """
    Khôi phục dấu tiếng Việt cho câu hỏi bằng LLM (gpt-4o-mini,
    temperature=0) - CHỈ dùng cho mục đích TRA CỨU tài liệu
    (search_query), KHÔNG thay đổi `message` gốc lưu vào DB/hiển thị cho
    người dùng (bước này phải hoàn toàn TRONG SUỐT với người dùng).

    ĐO ĐƯỢC QUA TEST THẬT: case "Ham de quy hoat dong nhu the nao?" (0
    kết quả tìm kiếm) -> sau khi khôi phục dấu thành "Hàm đệ quy hoạt
    động như thế nào?" -> 8 kết quả. Latency đo được ~1.1s/lượt (khoảng
    0.61s-2.13s).

    BẮT BUỘC temperature=0: prompt gốc (không có temperature=0) từng bị
    "trôi" (drift) sang TRẢ LỜI câu hỏi thay vì chỉ thêm dấu - PHÁT HIỆN
    QUA TEST THẬT khi điều tra trước đó. Prompt dưới đây đã được sửa và
    xác nhận ổn định, KHÔNG tự ý đổi lại nội dung prompt hay bỏ
    temperature=0.

    Fallback AN TOÀN: đây là bước TỐI ƯU chất lượng tìm kiếm, KHÔNG PHẢI
    bước bắt buộc của luồng chat - bất kỳ lỗi nào khi gọi API (timeout,
    lỗi mạng, lỗi bất kỳ) đều trả về `text` gốc thay vì raise, để không
    bao giờ làm hỏng/chặn cả câu hỏi của người dùng chỉ vì bước tối ưu
    phụ này gặp sự cố.
    """
    try:
        response = _client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Khôi phục dấu tiếng Việt cho câu sau, GIỮ NGUYÊN ý nghĩa và cấu trúc câu. "
                        "CHỈ trả về câu đã thêm dấu, KHÔNG trả lời câu hỏi, KHÔNG giải thích gì thêm."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        restored = response.choices[0].message.content
        return restored.strip() if restored else text
    except Exception:
        return text


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


def _apply_planner_result(
    result: PlannerResult,
    search_results: list[SearchResult],
) -> tuple[list[SearchResult], str]:
    """Chi dua evidence planner da chot cho composer; fallback giu legacy context."""
    if result.fallback_used:
        return search_results, ""

    selected_ids = {
        chunk_id
        for claim in result.plan.claims
        for chunk_id in claim.evidence_chunk_ids
    }
    selected = [item for item in search_results if item.chunk_id in selected_ids]
    # Planner co the chot insufficient ma khong co claim. Khong dua cac chunk bi
    # loai vao composer; day la khac biet cot loi so voi legacy direct RAG.
    if result.plan.answer_mode == "insufficient":
        selected = []
    elif not selected and search_results:
        # Schema dung nhung plan grounded rong: fallback an toan, khong lam giam
        # chat luong chi vi planner bo sot claim.
        return search_results, ""

    claims = "\n".join(
        f"- {claim.claim_id}: {claim.point} (chunks: {claim.evidence_chunk_ids})"
        for claim in result.plan.claims
    ) or "- Khong co claim du evidence de tra loi truc tiep."
    instruction = (
        "\n\nKE HOACH EVIDENCE DA DUOC KIEM TRA:\n"
        f"Answer mode: {result.plan.answer_mode}\n"
        f"Teaching strategy: {result.plan.teaching_strategy}\n"
        f"Claims duoc phep:\n{claims}\n"
        "Khong them factual claim moi ngoai danh sach tren."
    )
    return selected, instruction


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
    Suy ra Conversation này thuộc lớp nào từ các chunk đã tra cứu, nhưng
    chỉ khi toàn bộ kết quả cùng chỉ tới đúng một lớp.

    VÌ SAO CẦN: Dashboard giảng viên (app/instructor/) thống kê theo
    Conversation.course_id - nếu cột đó luôn NULL thì mọi số liệu bằng
    0 dù sinh viên hỏi bao nhiêu đi nữa (PHÁT HIỆN QUA TEST THẬT: mọi
    hội thoại trước đó đều có course_id=NULL vì client không gửi kèm).

    GIỚI HẠN CÓ CHỦ Ý: câu CHITCHAT/OFF_TOPIC không tra cứu tài liệu
    nên không suy ra được gì (trả None, Conversation giữ NULL) - chấp
    nhận được vì những câu đó không mang ý nghĩa thống kê học thuật.
    Nếu kết quả thuộc nhiều lớp thì trả None để tránh dùng suy luận mơ
    hồ cho dữ liệu học tập cá nhân. Nếu client gửi course_id tường minh,
    giá trị đó được ưu tiên và không dùng hàm này.
    """
    if not search_results:
        return None

    course_ids = {result.course_id for result in search_results}
    # Không âm thầm chọn lớp theo đa số khi retrieval trả tài liệu của
    # nhiều lớp. Lớp suy luận mơ hồ không đủ cơ sở để nạp dữ liệu cá nhân.
    return next(iter(course_ids)) if len(course_ids) == 1 else None


async def _has_no_enrollment(session: AsyncSession, user_id: int) -> bool:
    """
    True khi user CHƯA thuộc lớp học nào.

    Vì sao cần kiểm tra RIÊNG thay vì để Hybrid Search tự trả rỗng: ACL
    (app/retrieval/access_policy.py) lọc theo lớp user đã tham gia, nên
    user 0 lớp LUÔN nhận 0 đoạn - đúng luật, nhưng khi đó Nova trả lời
    "tài liệu hiện có chưa đề cập đủ thông tin", khiến sinh viên tưởng
    kho tài liệu thiếu nội dung trong khi nguyên nhân thật là họ chưa
    được thêm vào lớp. Phát hiện sớm ở đây còn tiết kiệm luôn 1 lượt
    gọi API embedding + 2 câu SQL chắc chắn không ra kết quả.

    KHÁC với nhánh SYSTEM_QUESTION (system_kb_service.py): nhánh đó trả
    lời câu hỏi VỀ hệ thống ("làm sao vào lớp"), còn hàm này xử lý câu
    hỏi HỌC THUẬT của người chưa có lớp nào.
    """
    result = await session.execute(
        text("SELECT COUNT(*) FROM enrollment WHERE user_id = :uid"), {"uid": user_id}
    )
    return (result.scalar() or 0) == 0


def _extract_retrieval_similarity(
    search_results: list[SearchResult], retrieval_stats: dict | None = None
) -> float | None:
    """
    Độ khớp tài liệu của lượt hỏi này - cosine similarity cao nhất giữa
    câu hỏi và các đoạn tài liệu tìm được (xem SearchResult.
    retrieval_similarity, mọi phần tử mang cùng 1 giá trị).

    Phân biệt RÕ 3 trạng thái (trước đây 2 trạng thái sau bị gộp làm
    một thành NULL, khiến mọi thống kê "insufficient context" nói dối):

    - None      = KHÔNG hề tra cứu (chitchat/off-topic, hoặc user chưa
                  vào lớp nào nên đã chốt sớm trước retrieval).
    - < ngưỡng  = CÓ tra cứu nhưng không đoạn nào đủ gần -> lấy số đo
                  thật từ retrieval_stats["best_similarity"], nhờ đó
                  giảng viên thấy được "gần sát ngưỡng" (0.29) khác
                  hẳn "lạc đề hoàn toàn" (0.05).
    - >= ngưỡng = CÓ tra cứu và tìm được (lấy từ chính kết quả).
    """
    if search_results:
        return search_results[0].retrieval_similarity
    if retrieval_stats and "best_similarity" in retrieval_stats:
        return retrieval_stats["best_similarity"]
    return None


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


def _build_planned_citations(evidence_plan, search_results: list[SearchResult]) -> list[dict]:
    lookup = {item.chunk_id: item for item in search_results}
    return [
        {
            "chunk_id": chunk_id,
            "document_id": lookup[chunk_id].document_id,
            "page_number": lookup[chunk_id].page_number,
        }
        for chunk_id in planned_citation_ids(evidence_plan, search_results)
        if chunk_id in lookup
    ]


async def handle_chat(
    session: AsyncSession,
    *,
    user_id: int,
    user_role: str | None = None,
    is_admin: bool = False,
    message: str,
    conversation_id: int | None = None,
    course_id: int | None = None,
    is_group: bool = False,
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
        history = await _fetch_recent_history(session, conversation_id, user_id)
    deadline_already_alerted = await _conversation_has_deadline_alert(
        session, conversation_id, user_id
    )

    active_course_id = await _resolve_active_course_id(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        requested_course_id=course_id,
    )
    role_context = await resolve_role_context(
        session,
        user_id=user_id,
        global_role=user_role or ("ADMIN" if is_admin else "STUDENT"),
        course_id=active_course_id,
    )
    if active_course_id is not None and not role_context.has_course_access:
        active_course_id = None
        role_context = await resolve_role_context(
            session,
            user_id=user_id,
            global_role=user_role or ("ADMIN" if is_admin else "STUDENT"),
            course_id=None,
        )
    instructor_context_block = build_instructor_context_block(await load_instructor_context(
        session, course_id=active_course_id, effective_role=role_context.effective_role
    ))
    preference = await get_preference(session, user_id)
    agentic_rollout_enabled = is_user_in_rollout(user_id, get_settings().nova_rollout_percent)
    personalization_instruction = build_personalization_instruction(
        build_personalization_context(preference, is_group=is_group)
    )
    memory_instruction = "" if is_group else build_memory_instruction(
        await load_conversation_memory(session, conversation_id, user_id)
    )

    # --- Bước 1+2 CHẠY SONG SONG: Guardrail input và Router classify ---
    # PHÁT HIỆN QUA ĐO THẬT (không phải đoán): 2 bước này tuần tự tốn
    # ~8s cộng dồn (mỗi bước ~4s, đều là round-trip gọi OpenAI), trong
    # khi CHÚNG KHÔNG PHỤ THUỘC NHAU - cả 2 chỉ cần đúng `message` +
    # `history`, Router không cần biết Guardrail đã cho qua hay chưa để
    # BẮT ĐẦU phân loại. Nếu Guardrail chặn, kết quả classify chỉ đơn
    # giản bị BỎ QUA ở nhánh dưới - lãng phí đúng 1 lượt gọi LLM rẻ cho
    # trường hợp bị chặn (hiếm), đổi lại tiết kiệm ~4s độ trễ NGƯỜI DÙNG
    # THẤY ĐƯỢC ở mọi câu hỏi hợp lệ (đa số) - đánh đổi hợp lý.
    #
    # Vector câu hỏi cũng được tính NGAY tại đây (song song, không đợi 2
    # bước trên) vì cùng lý do - xem giải thích đầy đủ ở
    # handle_chat_stream(). Chỉ bỏ qua khi câu hỏi cần viết lại theo ngữ
    # cảnh, vì lúc đó vector phụ thuộc kết quả bước viết lại.
    needs_rewrite = bool(history) and _looks_context_dependent(message)

    async def _embed_early():
        if needs_rewrite:
            return None
        return await asyncio.to_thread(lambda: embed_texts([message])[0])

    # Tải "câu quiz vừa làm sai" SONG SONG với Guardrail/Router, CÙNG lý
    # do và CÙNG hàm với handle_chat_stream() (xem load_student_context)
    # - trước đây handle_chat() KHÔNG gọi hàm này (không cần student_model
    # cho SOCRATIC_REQUEST ở luồng non-streaming theo thiết kế cũ), nay
    # cần thêm để nhánh RAG_QUESTION/SOCRATIC_REQUEST của endpoint
    # /v1/chat cũng biết được câu sai gần đây, nhất quán với streaming.
    input_check, route, early_vector, student_context = await asyncio.gather(
        asyncio.to_thread(check_input, message),
        asyncio.to_thread(classify, message, history),
        _embed_early(),
        (
            asyncio.sleep(0, result=StudentContext())
            if is_group
            else load_student_context(
                session,
                user_id=user_id,
                course_id=active_course_id,
                user_role=role_context.effective_role,
            )
        ),
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
    conversation = await _get_or_create_conversation(
        session, conversation_id, user_id, active_course_id
    )

    # --- Bước 3.5: System Knowledge Query (chỉ nếu SYSTEM_QUESTION) ---
    # Kiểm tra System Knowledge Base TRƯỚC khi xử lý retrieval thông thường.
    # Nếu có câu trả lời từ KB -> dùng ngay, không cần tra tài liệu.
    if route.category == "SYSTEM_QUESTION":
        kb_querier = SystemKBQuerier(session)
        kb_result = await kb_querier.query(message, user_id, role_context.effective_role)

        if kb_result.answer:
            # Có câu trả lời từ System Knowledge Base -> dùng luôn
            session.add(Message(conversation_id=conversation.id, role="user", content=message))
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=kb_result.answer,
                    category="SYSTEM_QUESTION",
                    needs_retrieval=False,
                )
            )
            await session.commit()
            return ChatResult(
                conversation_id=conversation.id,
                answer=kb_result.answer,
                category="SYSTEM_QUESTION",
                citations=[],
            )
        # Không match KB -> falls through để xử lý bình thường (LLM dùng system knowledge)

    # --- Bước 3.6: ACTION_REQUEST - function-calling, KHÔNG qua Retrieval/Generate ---
    # Đặt SAU System Knowledge Query, TRƯỚC Hybrid Search - cùng vị trí
    # "category có xử lý ĐẶC BIỆT" như nhánh SYSTEM_QUESTION ở trên (xem
    # docstring _handle_action_request_turn() để hiểu toàn bộ luồng).
    if route.category == "ACTION_REQUEST":
        # user_result cần cho _handle_action_request_turn (RBAC dùng
        # AppUser đầy đủ, không chỉ user_id) - route/classify chỉ có
        # user_id/is_admin, phải tra lại đúng đối tượng AppUser ở đây.
        user_result = await session.execute(select(AppUser).where(AppUser.id == user_id))
        current_user = user_result.scalar_one()

        outcome = await _handle_action_request_turn(
            session,
            conversation_id=conversation.id,
            user=current_user,
            message=message,
            role_context=role_context,
        )

        session.add(Message(conversation_id=conversation.id, role="user", content=message))
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=outcome.answer_text,
                category="ACTION_REQUEST",
                needs_retrieval=False,
                pending_action=outcome.pending_action_json,
            )
        )
        await session.commit()

        return ChatResult(
            conversation_id=conversation.id,
            answer=outcome.answer_text,
            category="ACTION_REQUEST",
            citations=[],
            pending_action=outcome.pending_action,
            action_result=outcome.action_result,
        )

    # --- Bước 4: Hybrid Search (chỉ nếu cần) ---
    search_results: list[SearchResult] = []
    # dict nhận số đo độ tương đồng từ hybrid_search kể cả khi kết quả
    # rỗng vì dưới ngưỡng - xem _extract_retrieval_similarity().
    retrieval_stats: dict = {}
    if route.needs_retrieval:
        # CHỐT SỚM: user chưa vào lớp nào -> mọi tra cứu chắc chắn ra 0
        # đoạn (ACL), trả lời thẳng đúng nguyên nhân thay vì để Nova
        # đổ lỗi cho kho tài liệu (xem _has_no_enrollment).
        if await _has_no_enrollment(session, user_id):
            session.add(Message(conversation_id=conversation.id, role="user", content=message))
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=NO_ENROLLMENT_MESSAGE,
                    category=route.category,
                    needs_retrieval=False,
                )
            )
            await session.commit()
            return ChatResult(
                conversation_id=conversation.id,
                answer=NO_ENROLLMENT_MESSAGE,
                category=route.category,
                citations=[],
            )

        search_query = message
        if needs_rewrite:
            search_query = await asyncio.to_thread(_rewrite_query_with_history, message, history)

        # Khôi phục dấu tiếng Việt CHO MỤC ĐÍCH TRA CỨU (search_query) -
        # chạy SAU bước viết lại theo ngữ cảnh (nếu câu vừa ngắn/phụ
        # thuộc ngữ cảnh vừa mất dấu, rewrite chạy trước trên câu gốc,
        # rồi khôi phục dấu chạy trên kết quả đã rewrite). Đây là bước
        # ĐỘC LẬP với needs_rewrite (xem _looks_like_unaccented_
        # vietnamese) - ~31% traffic thật là tiếng Việt không dấu, phần
        # lớn KHÔNG thoả điều kiện needs_rewrite (câu dài, độc lập ngữ
        # nghĩa) nên phải kiểm tra riêng, không gộp chung 2 điều kiện.
        #
        # `message` KHÔNG bị đổi (vẫn lưu nguyên văn vào DB/hiển thị cho
        # user) - chỉ `search_query` dùng để tra cứu bị thay đổi.
        query_was_rewritten = needs_rewrite
        if _looks_like_unaccented_vietnamese(search_query):
            search_query = await asyncio.to_thread(_restore_vietnamese_accents, search_query)
            query_was_rewritten = True

        search_results = await hybrid_search(
            session,
            query_text=search_query,
            user_id=user_id,
            is_admin=is_admin,
            # early_vector chỉ còn đúng nếu search_query KHÔNG bị đổi bởi
            # rewrite HAY khôi phục dấu - nếu 1 trong 2 đã chạy, câu tra
            # cứu cuối cùng khác với `message` gốc dùng để tính
            # early_vector, phải để hybrid_search tự embed lại.
            query_vector=None if query_was_rewritten else early_vector,
            stats=retrieval_stats,
            course_id=active_course_id,
        )

    planner_instruction = ""
    evidence_plan = None
    if route.needs_retrieval:
        planner_result = await asyncio.to_thread(
            plan_evidence,
            question=message,
            search_query=search_query,
            candidates=search_results,
            history=history,
            effective_role=role_context.effective_role,
            socratic=route.category == "SOCRATIC_REQUEST",
            enabled=agentic_rollout_enabled,
        )
        search_results, _legacy_planner_instruction = _apply_planner_result(
            planner_result, search_results
        )
        if not planner_result.fallback_used:
            evidence_plan = planner_result.plan
            planner_instruction = build_plan_instruction(
                evidence_plan, is_first_message=not history
            )
        else:
            planner_instruction = _legacy_planner_instruction

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
    recent_mistake_block = ""
    if route.category in ("RAG_QUESTION", "SOCRATIC_REQUEST"):
        recent_mistake_block = build_recent_mistake_block(student_context.recent_mistake)
    learning_progress_block = build_learning_progress_block(student_context)
    deadline_alert_block = build_deadline_alert_block(
        student_context,
        already_alerted=deadline_already_alerted,
    )

    context_text = (
        _build_context_text(search_results)
        + planner_instruction
        + personalization_instruction
        + memory_instruction
    )
    # history rỗng = lượt hỏi đầu tiên của phiên -> cho phép Nova chào
    # một câu ngắn. Các lượt sau vào thẳng nội dung (xem prompts.py).
    system_prompt = build_system_prompt(
        route.category,
        context_text,
        is_first_message=not history,
        recent_mistake=recent_mistake_block,
        learning_progress=learning_progress_block,
        deadline_alert=deadline_alert_block,
        instructor_context=instructor_context_block,
        effective_role=role_context.effective_role,
        active_course_id=active_course_id,
    )
    model = get_model_for_category(route.category)
    temperature = get_temperature_for_category(route.category)

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]

    # needs_retrieval=True -> prompt đã yêu cầu JSON contract (answer +
    # citations kèm quote) để Citation Verification hoạt động - CHITCHAT/
    # OFF_TOPIC không cần citation, giữ nguyên text thường (không tốn
    # thêm độ phức tạp parse JSON cho câu không cần trích dẫn nào).
    def _call_llm() -> str:
        kwargs = {"model": model, "messages": messages}
        if route.needs_retrieval:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = _client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    if route.needs_retrieval:
        composer_result = await asyncio.to_thread(
            compose_grounded_response,
            messages=messages,
            model=model,
            temperature=temperature,
            plan=evidence_plan,
            candidates=search_results,
            is_first_message=not history,
            enabled=agentic_rollout_enabled,
        )
        if composer_result.fallback_used:
            raw_response = await asyncio.to_thread(_call_llm)
            answer, raw_citations = _parse_llm_response(raw_response)
        else:
            answer = composer_result.answer
            raw_citations = composer_result.citations
    else:
        raw_response = await asyncio.to_thread(_call_llm)
        answer, raw_citations = raw_response, []

    if route.category == "SOCRATIC_REQUEST":
        answer = normalize_socratic_answer(answer)

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
    citations = _build_planned_citations(evidence_plan, search_results)
    if not citations:
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
            retrieval_similarity=_extract_retrieval_similarity(search_results, retrieval_stats),
        )
    )
    await session.flush()
    await refresh_conversation_memory(session, conversation.id, user_id)
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
    user_role: str | None = None,
    is_admin: bool = False,
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
    request_start = time.monotonic()

    # Báo tiến trình cho người dùng NGAY LẬP TỨC, trước cả khi làm gì.
    #
    # VÌ SAO CẦN: từ lúc gửi câu hỏi tới lúc chữ đầu tiên hiện ra mất
    # khoảng 2 giây (kiểm tra an toàn + phân loại + tìm tài liệu). Nếu
    # màn hình im lặng suốt khoảng đó, người dùng không phân biệt được
    # "đang xử lý" với "bị treo". Các sự kiện status này KHÔNG làm hệ
    # thống nhanh hơn - chúng làm cho việc chờ đợi có thể hiểu được.
    yield {"type": "status", "stage": "checking"}

    history: list[dict] = []
    if conversation_id is not None:
        history = await _fetch_recent_history(session, conversation_id, user_id)
    deadline_already_alerted = await _conversation_has_deadline_alert(
        session, conversation_id, user_id
    )

    active_course_id = await _resolve_active_course_id(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        requested_course_id=course_id,
    )
    role_context = await resolve_role_context(
        session,
        user_id=user_id,
        global_role=user_role or ("ADMIN" if is_admin else "STUDENT"),
        course_id=active_course_id,
    )
    if active_course_id is not None and not role_context.has_course_access:
        active_course_id = None
        role_context = await resolve_role_context(
            session,
            user_id=user_id,
            global_role=user_role or ("ADMIN" if is_admin else "STUDENT"),
            course_id=None,
        )
    instructor_context_block = build_instructor_context_block(await load_instructor_context(
        session, course_id=active_course_id, effective_role=role_context.effective_role
    ))
    preference = await get_preference(session, user_id)
    agentic_rollout_enabled = is_user_in_rollout(user_id, get_settings().nova_rollout_percent)
    personalization_instruction = build_personalization_instruction(
        build_personalization_context(preference, is_group=False)
    )
    memory_instruction = build_memory_instruction(
        await load_conversation_memory(session, conversation_id, user_id)
    )

    # Tải hồ sơ học tập (khái niệm của lớp + mức độ nắm vững) SONG SONG
    # với Guardrail và Router - 3 việc này KHÔNG phụ thuộc kết quả của
    # nhau, chạy nối tiếp là lãng phí thời gian người dùng phải chờ.
    #
    # Tải cho MỌI câu hỏi (không chỉ chế độ gia sư): danh sách khái
    # niệm còn dùng để NHẬN DIỆN câu hỏi thuộc chủ đề nào, phục vụ Gap
    # Analysis của giảng viên ("sinh viên hỏi nhiều về chủ đề X nhưng
    # tài liệu không đáp ứng được"). Đây là 1 truy vấn nhỏ chạy song
    # song, không thêm độ trễ mà người dùng cảm nhận được.
    async def _load_context_if_needed():
        return await load_student_context(
            session,
            user_id=user_id,
            course_id=active_course_id,
            user_role=role_context.effective_role,
        )

    # Tính LUÔN vector câu hỏi ở giai đoạn này, song song với Guardrail/
    # Router - ĐO ĐƯỢC QUA SỐ LIỆU THẬT: trước đây embedding chạy nối
    # tiếp SAU khi Guardrail/Router xong, cộng thẳng ~1.2s vào khoảng
    # thời gian người dùng nhìn màn hình trắng (chưa thấy chữ nào).
    # Embedding KHÔNG phụ thuộc kết quả 2 bước kia nên không có lý do
    # phải đợi.
    #
    # CHỈ làm được khi câu hỏi TỰ ĐẦY ĐỦ Ý NGHĨA: câu ngắn/phụ thuộc
    # ngữ cảnh ("cho ví dụ?") phải qua bước viết lại bằng LLM trước
    # (_rewrite_query_with_history) rồi mới embed được - lúc đó vector
    # thật sự phụ thuộc bước trước, đành chạy nối tiếp như cũ.
    #
    # Đánh đổi: câu bị Guardrail chặn vẫn tốn 1 lượt embedding (~$0.000002)
    # dù kết quả bị bỏ đi - không đáng kể so với vài giây tiết kiệm được
    # cho MỌI câu hỏi hợp lệ.
    needs_rewrite = bool(history) and _looks_context_dependent(message)
    can_embed_early = not needs_rewrite

    async def _embed_early():
        if not can_embed_early:
            return None
        return await asyncio.to_thread(lambda: embed_texts([message])[0])

    guardrail_router_start = time.monotonic()
    if force_category in ("RAG_QUESTION", "SOCRATIC_REQUEST"):
        input_check, route, student_context, early_vector = await asyncio.gather(
            asyncio.to_thread(check_input, message),
            asyncio.sleep(0, result=RouteResult(
                category=force_category,
                reasoning="Người dùng chọn tường minh qua tab ChatBubble.",
                needs_retrieval=True,
                classified_by="forced",
            )),
            _load_context_if_needed(),
            _embed_early(),
        )
    else:
        input_check, route, student_context, early_vector = await asyncio.gather(
            asyncio.to_thread(check_input, message),
            asyncio.to_thread(classify, message, history),
            _load_context_if_needed(),
            _embed_early(),
        )
    guardrail_router_ms = int((time.monotonic() - guardrail_router_start) * 1000)

    if not input_check.allowed:
        await _log_security_block(
            session, user_id, "input", input_check.blocked_by, input_check.reason, message
        )
        yield {"type": "blocked", "conversation_id": conversation_id or 0, "reason": "invalid"}
        return

    conversation = await _get_or_create_conversation(
        session, conversation_id, user_id, active_course_id
    )

    # Kho kiến trúc nội bộ tách hoàn toàn khỏi chỉ mục tài liệu lớp. Chỉ role
    # OWNER đã được get_current_user xác minh mới có thể đi vào nhánh này.
    if user_role == "OWNER":
        yield {"type": "status", "stage": "retrieving"}
        answer = await asyncio.to_thread(_answer_owner_learning_question, message, history)
        output_check = await asyncio.to_thread(check_output, answer)
        if not output_check.allowed:
            await _log_security_block(
                session, user_id, "output", output_check.blocked_by, output_check.reason, answer
            )
            answer = "Mình không thể trả lời nội dung đó. Bro thử hỏi lại theo hướng kiến thức kỹ thuật nhé."

        yield {
            "type": "start",
            "conversation_id": conversation.id,
            "category": "INTERNAL_LEARNING",
            "concept_id": None,
        }
        words = answer.split()
        for index, word in enumerate(words):
            yield {"type": "chunk", "text": word + (" " if index < len(words) - 1 else "")}

        session.add(Message(conversation_id=conversation.id, role="user", content=message))
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            category="RAG_QUESTION",
            needs_retrieval=True,
        )
        session.add(assistant_message)
        await session.commit()
        yield {
            "type": "done",
            "citations": [],
            "message_id": assistant_message.id,
            "retrieval_similarity": None,
        }
        return

    # --- System Knowledge Query (chỉ nếu SYSTEM_QUESTION) ---
    # Kiểm tra System Knowledge Base TRƯỚC khi xử lý retrieval.
    if route.category == "SYSTEM_QUESTION":
        kb_querier = SystemKBQuerier(session)
        kb_result = await kb_querier.query(message, user_id, role_context.effective_role)

        if kb_result.answer:
            # Có câu trả lời từ KB -> stream từng từ
            yield {
                "type": "start",
                "conversation_id": conversation.id,
                "category": "SYSTEM_QUESTION",
                "concept_id": None,
            }
            # Stream từng từ để用户体验一致
            words = kb_result.answer.split()
            for i, word in enumerate(words):
                yield {"type": "chunk", "text": word + (" " if i < len(words) - 1 else "")}

            session.add(Message(conversation_id=conversation.id, role="user", content=message))
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=kb_result.answer,
                    category="SYSTEM_QUESTION",
                    needs_retrieval=False,
                )
            )
            await session.commit()
            yield {
                "type": "done",
                "citations": [],
                "message_id": None,
                "retrieval_similarity": None,
            }
            return

    # --- ACTION_REQUEST - function-calling, KHÔNG qua Retrieval/Generate ---
    # Cùng vị trí "category có xử lý ĐẶC BIỆT" như SYSTEM_QUESTION ở
    # trên, cùng logic LÕI với handle_chat() (xem
    # _handle_action_request_turn()) - chỉ khác ở CÁCH phát sự kiện SSE:
    # "status" trước khi gọi LLM tool-call, rồi "action_pending" HOẶC
    # "action_result" (2 event type MỚI - xem VIỆC 7 trong kế hoạch),
    # KHÔNG stream từng chữ như category khác vì câu trả lời ở đây
    # thường ngắn và mang tính XÁC NHẬN/KẾT QUẢ hơn là văn bản dài.
    if route.category == "ACTION_REQUEST":
        yield {"type": "status", "stage": "generating"}

        user_result = await session.execute(select(AppUser).where(AppUser.id == user_id))
        current_user = user_result.scalar_one()

        outcome = await _handle_action_request_turn(
            session,
            conversation_id=conversation.id,
            user=current_user,
            message=message,
            role_context=role_context,
        )

        yield {
            "type": "start",
            "conversation_id": conversation.id,
            "category": "ACTION_REQUEST",
            "concept_id": None,
        }

        session.add(Message(conversation_id=conversation.id, role="user", content=message))
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=outcome.answer_text,
            category="ACTION_REQUEST",
            needs_retrieval=False,
            pending_action=outcome.pending_action_json,
        )
        session.add(assistant_message)
        await session.commit()

        if outcome.pending_action is not None:
            yield {
                "type": "action_pending",
                "tool_name": outcome.pending_action.tool_name,
                "tool_label_vi": outcome.pending_action.tool_label_vi,
                "arguments_summary": outcome.pending_action.arguments_summary,
            }
        elif outcome.action_result is not None:
            yield {
                "type": "action_result",
                "tool_name": outcome.action_result.tool_name,
                "tool_label_vi": outcome.action_result.tool_label_vi,
                "success": outcome.action_result.success,
                "summary": outcome.action_result.summary,
            }
        else:
            # Không tool nào được gọi (LLM tự trả lời text thường) -
            # vẫn stream nội dung để giao diện có gì đó hiển thị nhất
            # quán với các category khác (không chỉ im lặng rồi "done").
            yield {"type": "chunk", "text": outcome.answer_text}

        yield {
            "type": "done",
            "citations": [],
            "message_id": assistant_message.id,
            "retrieval_similarity": None,
        }
        return

    retrieval_start = time.monotonic()
    search_results: list[SearchResult] = []
    retrieval_stats: dict = {}
    query_vector: list[float] | None = None
    if route.needs_retrieval:
        # CHỐT SỚM cho user chưa vào lớp nào - cùng lý do với
        # handle_chat(), chỉ khác ở dạng sự kiện SSE phải phát ra đủ bộ
        # start/chunk/done để Frontend không treo ở trạng thái "đang gõ".
        if await _has_no_enrollment(session, user_id):
            yield {
                "type": "start",
                "conversation_id": conversation.id,
                "category": route.category,
                "concept_id": None,
            }
            yield {"type": "chunk", "text": NO_ENROLLMENT_MESSAGE}

            session.add(Message(conversation_id=conversation.id, role="user", content=message))
            no_enroll_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=NO_ENROLLMENT_MESSAGE,
                category=route.category,
                needs_retrieval=False,
            )
            session.add(no_enroll_message)
            await session.commit()
            yield {
                "type": "done",
                "citations": [],
                "message_id": no_enroll_message.id,
                "retrieval_similarity": None,
            }
            return

        yield {"type": "status", "stage": "searching"}
        search_query = message
        if needs_rewrite:
            search_query = await asyncio.to_thread(_rewrite_query_with_history, message, history)

        # Khôi phục dấu tiếng Việt CHO MỤC ĐÍCH TRA CỨU (search_query) -
        # chạy SAU bước viết lại theo ngữ cảnh, giống hệt logic trong
        # handle_chat() (xem giải thích đầy đủ ở đó). Bước ĐỘC LẬP với
        # needs_rewrite - không phụ thuộc độ dài câu hay có lịch sử hay
        # không, chỉ dựa trên _looks_like_unaccented_vietnamese.
        #
        # `message` KHÔNG bị đổi (vẫn lưu nguyên văn vào DB/hiển thị cho
        # user) - chỉ `search_query` dùng để tra cứu (và từ đó, vector
        # dùng để so khớp khái niệm - concept_matcher) bị thay đổi.
        query_was_rewritten = needs_rewrite
        if _looks_like_unaccented_vietnamese(search_query):
            search_query = await asyncio.to_thread(_restore_vietnamese_accents, search_query)
            query_was_rewritten = True

        # Tính vector câu hỏi 1 LẦN DUY NHẤT rồi dùng cho CẢ 2 việc:
        # tìm tài liệu (Hybrid Search) và xác định khái niệm đang hỏi
        # (concept_matcher) - không gọi API embedding lần thứ hai.
        #
        # early_vector CHỈ còn dùng được nếu search_query KHÔNG bị đổi
        # bởi rewrite HAY khôi phục dấu (query_was_rewritten=False) - nếu
        # 1 trong 2 bước trên đã chạy, early_vector (tính từ `message`
        # gốc) không còn khớp với search_query cuối cùng, phải embed lại.
        if early_vector is not None and not query_was_rewritten:
            query_vector = early_vector
        else:
            query_vector = await asyncio.to_thread(lambda: embed_texts([search_query])[0])
        search_results = await hybrid_search(
            session,
            query_text=search_query,
            user_id=user_id,
            query_vector=query_vector,
            is_admin=is_admin,
            stats=retrieval_stats,
            course_id=active_course_id,
        )
    retrieval_ms = int((time.monotonic() - retrieval_start) * 1000)

    planner_instruction = ""
    evidence_plan = None
    if route.needs_retrieval:
        planner_result = await asyncio.to_thread(
            plan_evidence,
            question=message,
            search_query=search_query,
            candidates=search_results,
            history=history,
            effective_role=role_context.effective_role,
            socratic=route.category == "SOCRATIC_REQUEST",
            enabled=agentic_rollout_enabled,
        )
        search_results, _legacy_planner_instruction = _apply_planner_result(
            planner_result, search_results
        )
        if not planner_result.fallback_used:
            evidence_plan = planner_result.plan
            planner_instruction = build_plan_instruction(
                evidence_plan, is_first_message=not history
            )
        else:
            planner_instruction = _legacy_planner_instruction

    # Báo đã tìm xong tài liệu, sắp soạn câu trả lời. Kèm SỐ ĐOẠN tìm
    # được để người dùng thấy hệ thống có căn cứ thật (hoặc biết ngay là
    # không tìm thấy gì, thay vì bất ngờ khi đọc câu trả lời "tôi không
    # có đủ thông tin").
    yield {"type": "status", "stage": "generating", "sources_found": len(search_results)}

    # Gắn Conversation vào đúng lớp học nếu client chưa chỉ định - xem
    # docstring _infer_course_id (cùng logic với handle_chat()).
    if conversation.course_id is None:
        inferred_course_id = _infer_course_id(search_results)
        if inferred_course_id is not None:
            conversation.course_id = inferred_course_id

    # Xác định câu hỏi thuộc khái niệm nào - phép tính trong bộ nhớ,
    # không gọi API, ~0ms (vector câu hỏi đã có sẵn từ bước tìm kiếm).
    # Ưu tiên lựa chọn TƯỜNG MINH của sinh viên (họ sửa lại khi hệ
    # thống đoán sai).
    #
    # Chạy cho MỌI câu hỏi, dùng vào 2 việc khác nhau:
    # - Chế độ gia sư: đọc mức độ nắm vững để điều chỉnh cách dẫn dắt.
    # - Mọi chế độ: lưu vào Message để giảng viên biết sinh viên hay
    #   hỏi chủ đề nào mà tài liệu không đáp ứng được (Gap Analysis).
    student_model_block = ""
    matched_concept_id: int | None = None
    concept_name: str | None = None

    if student_context.concepts:
        if concept_id is not None:
            matched_concept_id = concept_id
            concept_name = next(
                (name for cid, name, _ in student_context.concepts if cid == concept_id), None
            )
        elif query_vector is not None:
            match = find_best_concept(query_vector, student_context.concepts)
            matched_concept_id = match.concept_id if match else None
            concept_name = match.concept_name if match else None

        # Mô hình người học CHỈ dùng cho chế độ gia sư - chế độ hỏi đáp
        # thường không cần điều chỉnh theo mức độ nắm vững.
        if (
            route.category == "SOCRATIC_REQUEST"
            and matched_concept_id is not None
            and concept_name is not None
        ):
            m = student_context.mastery_for(matched_concept_id)
            student_model_block = build_student_model_block(
                concept_name=concept_name,
                mastered=m.mastered,
                n_obs=m.n_obs,
                n_correct=m.n_correct,
                streak=m.streak,
            )

    # Câu quiz sai gần đây nhất - chèn cho RAG_QUESTION và
    # SOCRATIC_REQUEST (sinh viên hỏi "giải thích câu vừa rồi" hay bị
    # phân loại vào 1 trong 2 category này, KHÔNG BAO GIỜ là
    # ACTION_REQUEST - xem chú thích đầy đủ ở _RECENT_MISTAKE_BLOCK
    # trong prompts.py). Category khác build_system_prompt tự bỏ qua.
    recent_mistake_block = ""
    if route.category in ("RAG_QUESTION", "SOCRATIC_REQUEST"):
        recent_mistake_block = build_recent_mistake_block(student_context.recent_mistake)
    learning_progress_block = build_learning_progress_block(student_context)
    deadline_alert_block = build_deadline_alert_block(
        student_context,
        already_alerted=deadline_already_alerted,
    )

    context_text = (
        _build_context_text(search_results)
        + planner_instruction
        + personalization_instruction
        + memory_instruction
    )
    # with_citation_contract=False: luồng streaming đẩy thẳng text ra
    # màn hình, không parse JSON - xem docstring build_system_prompt.
    system_prompt = build_system_prompt(
        route.category,
        context_text,
        student_model_block,
        with_citation_contract=False,
        is_first_message=not history,
        recent_mistake=recent_mistake_block,
        learning_progress=learning_progress_block,
        deadline_alert=deadline_alert_block,
        instructor_context=instructor_context_block,
        effective_role=role_context.effective_role,
        active_course_id=active_course_id,
    )
    model = get_model_for_category(route.category)
    temperature = get_temperature_for_category(route.category)
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
    # Nơi thread nền ghi lại usage token đọc từ chunk CUỐI CÙNG của
    # stream (xem stream_options bên dưới) - dict rỗng vì thread nền
    # không return được giá trị trực tiếp cho async generator này.
    usage_holder: dict = {}

    def _stream_worker():
        try:
            # stream_options={"include_usage": True}: BẮT BUỘC để nhận
            # được token usage khi stream=True - mặc định OpenAI KHÔNG
            # trả usage cho response dạng stream, chỉ khi bật cờ này
            # (đã xác nhận bằng test thật, không phải suy đoán từ tài
            # liệu). Không có nó, Cost Dashboard sẽ luôn thiếu chi phí
            # của bước ĐẮT NHẤT (sinh câu trả lời).
            stream_kwargs = {
                "model": model,
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if temperature is not None:
                stream_kwargs["temperature"] = temperature
            stream = _client.chat.completions.create(**stream_kwargs)
            for chunk in stream:
                if chunk.usage is not None:
                    usage_holder["input"] = chunk.usage.prompt_tokens
                    usage_holder["output"] = chunk.usage.completion_tokens
                if chunk.choices and chunk.choices[0].delta.content:
                    loop.call_soon_threadsafe(queue.put_nowait, chunk.choices[0].delta.content)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # tín hiệu kết thúc

    import threading

    generate_start = time.monotonic()
    threading.Thread(target=_stream_worker, daemon=True).start()

    full_answer_parts: list[str] = []
    while True:
        piece = await queue.get()
        if piece is None:
            break
        full_answer_parts.append(piece)
        yield {"type": "chunk", "text": piece}
    generate_ms = int((time.monotonic() - generate_start) * 1000)

    answer = "".join(full_answer_parts)

    # GIỚI HẠN CÓ CHỦ Ý (nói rõ, không giấu): chỉ đo token của bước
    # SINH CÂU TRẢ LỜI - bước tốn kém nhất (input gồm toàn bộ ngữ cảnh
    # tài liệu + lịch sử hội thoại). Router classify và Embedding tìm
    # kiếm CŨNG tốn token nhưng nhỏ hơn nhiều và chưa được đo ở phiên
    # bản đầu tiên này - đủ để Cost Dashboard phản ánh đúng XU HƯỚNG
    # chi phí, dù chưa phải con số tuyệt đối chính xác 100%.
    token_usage = {
        "generate": {
            "model": model,
            "input": usage_holder.get("input", 0),
            "output": usage_holder.get("output", 0),
        }
    }
    latency = {
        "guardrail_router_ms": guardrail_router_ms,
        "retrieval_ms": retrieval_ms,
        "generate_ms": generate_ms,
        "total_ms": int((time.monotonic() - request_start) * 1000),
    }

    citations = _build_citations(search_results)
    session.add(Message(conversation_id=conversation.id, role="user", content=message))
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        citations=json.dumps(citations, ensure_ascii=False) if citations else None,
        category=route.category,
        needs_retrieval=route.needs_retrieval,
        concept_id=matched_concept_id,
        token_usage=json.dumps(token_usage, ensure_ascii=False),
        latency_ms=json.dumps(latency, ensure_ascii=False),
        retrieval_similarity=_extract_retrieval_similarity(search_results, retrieval_stats),
    )
    session.add(assistant_message)
    await session.flush()
    await refresh_conversation_memory(session, conversation.id, user_id)
    await session.commit()

    # message_id + retrieval_similarity gửi kèm để giao diện biết đánh
    # giá 👍/👎 thuộc về tin nhắn nào và hiển thị "Độ khớp tài liệu".
    yield {
        "type": "done",
        "citations": citations,
        "message_id": assistant_message.id,
        "retrieval_similarity": assistant_message.retrieval_similarity,
    }

    # Guardrail output chạy Ở NỀN, KHÔNG chặn response đã stream xong -
    # xem docstring _run_output_guardrail_in_background để hiểu đánh đổi.
    asyncio.create_task(_run_output_guardrail_in_background(session_factory, user_id, answer))
