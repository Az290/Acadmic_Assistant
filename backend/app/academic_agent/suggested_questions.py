"""
Suggested Questions - sinh ra danh sách câu hỏi gợi ý dựa trên context.

Logic:
1. Lấy conversation hiện tại (các messages gần đây)
2. Phân tích topic/category đang thảo luận
3. Sinh 3-5 câu hỏi liên quan (dùng LLM hoặc rule-based)
"""

import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, Concept


# Câu hỏi mẫu theo category - fallback khi không có context
CATEGORY_QUESTIONS = {
    "RAG_QUESTION": [
        "Ban co the giai thich ro hon khong?",
        "Cho vi du cu the duoc khong?",
        "Co cach nao khac de giai quyet khong?",
        "Noi dung nay lien quan nhu the nao voi bai hoc truoc?",
        "Toi co the tim hieu them o dau?",
    ],
    "SOCRATIC_REQUEST": [
        "Mot cau hoi don gian de on tap?",
        "Cho toi lam mot bai kiem tra nho?",
        "Toi chua hieu cho nao, giup toi voi?",
    ],
    "CHITCHAT": [
        "Ban la ai?",
        "Ban co the gi gi do khong?",
    ],
    "OFF_TOPIC": [
        "Ban co the giup toi ve bai hoc khong?",
        "Tai lieu cua lop co gi moi khong?",
    ],
    "GENERAL_KNOWLEDGE": [
        "Ban co the cho toi biet them khong?",
        "Co the giai thich them khong?",
    ],
}


async def get_suggested_questions(
    session: AsyncSession,
    conversation_id: int,
    user_id: int,
    max_questions: int = 5,
) -> list[str]:
    """
    Lấy danh sách câu hỏi gợi ý.

    Args:
        session: Database session
        conversation_id: ID của conversation
        user_id: ID của user (để kiểm tra quyền)
        max_questions: Số câu hỏi tối đa trả về

    Returns:
        List of suggested question strings
    """
    # 1. Lấy conversation và messages
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,  # Chỉ own conversation
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        return _get_fallback_questions("RAG_QUESTION", max_questions)

    # 2. Lấy messages gần đây (5 cuối cùng)
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(5)
    )
    messages = list(reversed(result.scalars().all()))

    if not messages:
        return _get_fallback_questions("RAG_QUESTION", max_questions)

    # 3. Phân tích category của messages gần nhất
    latest_assistant_msg = None
    for msg in reversed(messages):
        if msg.role == "assistant":
            latest_assistant_msg = msg
            break

    category = "RAG_QUESTION"
    if latest_assistant_msg and latest_assistant_msg.category:
        category = latest_assistant_msg.category

    # 4. Lấy concepts liên quan nếu có
    concepts_covered = []
    for msg in messages:
        if msg.concept_id:
            result = await session.execute(
                select(Concept).where(Concept.id == msg.concept_id)
            )
            concept = result.scalar_one_or_none()
            if concept:
                concepts_covered.append(concept.name)

    # 5. Sinh câu hỏi dựa trên context
    suggestions = _generate_suggestions(category, concepts_covered, messages)

    return suggestions[:max_questions]


def _generate_suggestions(
    category: str,
    concepts: list[str],
    messages: list[Message],
) -> list[str]:
    """
    Sinh câu hỏi gợi ý dựa trên category và context.

    Hiện tại dùng rule-based với category questions.
    Có thể nâng cấp lên LLM-based generation sau.
    """
    base_questions = CATEGORY_QUESTIONS.get(category, CATEGORY_QUESTIONS["RAG_QUESTION"])

    suggestions = []

    # Thêm câu hỏi dựa trên category
    for q in base_questions[:3]:
        suggestions.append(q)

    # Thêm câu hỏi dựa trên concepts đã cover
    if concepts:
        for concept in concepts[:2]:
            suggestions.append(f"{concept} hoat dong nhu the nao?")

    # Thêm câu hỏi practice/test
    suggestions.append("Toi muon on tap lai bai nay")
    suggestions.append("Co bai tap nao de luyen tap khong?")

    return suggestions


def _get_fallback_questions(category: str, max_questions: int) -> list[str]:
    """Fallback khi không có context."""
    return CATEGORY_QUESTIONS.get(category, CATEGORY_QUESTIONS["RAG_QUESTION"])[:max_questions]
