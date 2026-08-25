"""
Tóm tắt cuộc trò chuyện - phân tích toàn bộ lịch sử hội thoại để
tạo summary, key points và covered concepts.
"""

import asyncio
import json
from datetime import datetime, timezone

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Conversation, Message

_settings = get_settings()
_client = OpenAI(api_key=_settings.openai_api_key)

SUMMARY_PROMPT = """Bạn là trợ lý phân tích cuộc trò chuyện học tập. Phân tích đoạn hội thoại dưới đây và trả về JSON theo đúng format.

QUY TẮC:
1. summary: Tóm tắt 1-2 câu về nội dung CHÍNH của cuộc trò chuyện (dưới 150 từ)
2. key_points: Danh sách 3-5 điểm quan trọng đã thảo luận (mỗi điểm 1 câu ngắn)
3. covered_concepts: Các khái niệm/chủ đề chính đã đề cập (danh sách tên cụ thể)
4. Trả về ĐÚNG format JSON, không kèm text khác

FORMAT JSON:
{
  "summary": "Tóm tắt ngắn gọn...",
  "key_points": ["Điểm 1", "Điểm 2", "Điểm 3"],
  "covered_concepts": ["Khái niệm A", "Khái niệm B", "Khái niệm C"]
}

HỘI THOẠI:
{conversation_text}
"""


async def summarize_conversation(
    session: AsyncSession,
    conversation_id: int,
    user_id: int,
    max_length: int = 150,
) -> dict | None:
    """
    Tóm tắt cuộc trò chuyện.

    Args:
        session: Database session
        conversation_id: ID của cuộc trò chuyện
        user_id: ID của người dùng (để xác minh quyền truy cập)
        max_length: Độ dài tối đa của summary (mặc định 150 từ)

    Returns:
        dict với keys: summary, key_points, covered_concepts, timestamp
        None nếu không tìm thấy conversation hoặc không có messages
    """
    # 1. Lấy conversation và kiểm tra quyền sở hữu
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        return None

    # 2. Lấy toàn bộ messages trong conversation
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = list(result.scalars().all())

    if len(messages) == 0:
        return None

    # 3. Format messages thành text để gửi cho LLM
    conversation_text = []
    for msg in messages:
        role_label = "Sinh viên" if msg.role == "user" else "Nova"
        conversation_text.append(f"{role_label}: {msg.content}")

    full_text = "\n\n".join(conversation_text)

    # 4. Gọi LLM để tạo summary (dùng gpt-4o-mini để tiết kiệm)
    def _call_llm() -> str:
        response = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là trợ lý phân tích cuộc trò chuyện học tập. Phân tích và trả về JSON đúng format.",
                },
                {
                    "role": "user",
                    "content": SUMMARY_PROMPT.format(conversation_text=full_text),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return response.choices[0].message.content

    try:
        raw_response = await asyncio.to_thread(_call_llm)
        parsed = json.loads(raw_response)
    except (json.JSONDecodeError, Exception):
        # Fallback: tạo summary đơn giản nếu LLM không trả về JSON hợp lệ
        parsed = {
            "summary": f"Cuộc trò chuyện gồm {len(messages)} tin nhắn về các câu hỏi học tập.",
            "key_points": ["Đã có cuộc trao đổi về nội dung học tập"],
            "covered_concepts": [],
        }

    # 5. Build và return structured response
    return {
        "summary": parsed.get("summary", ""),
        "key_points": parsed.get("key_points", []),
        "covered_concepts": parsed.get("covered_concepts", []),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
