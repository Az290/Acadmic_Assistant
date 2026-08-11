from datetime import datetime

from pydantic import BaseModel


class ConversationHistoryItem(BaseModel):
    """1 dòng lịch sử hỏi-đáp của CHÍNH người dùng - ghép từ 1 cặp
    (câu hỏi của user, câu trả lời của assistant) trong cùng conversation."""

    question: str
    category: str  # RAG_QUESTION | SOCRATIC_REQUEST | CHITCHAT | OFF_TOPIC
    created_at: datetime
    # Số trích dẫn (RAG_QUESTION) hoặc số lượt trao đổi trong phiên Socratic
    # (SOCRATIC_REQUEST) - None cho CHITCHAT/OFF_TOPIC (không có "nguồn").
    source_count: int | None
