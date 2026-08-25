"""
SystemKBQuerier - service để query System Knowledge Base.

Tích hợp vào agent.py để xử lý câu hỏi về CÁCH HỆ THỐNG hoạt động
(không phải nội dung môn học).

Logic:
1. Extract keywords từ câu hỏi
2. Query SystemKnowledge by keyword + category
3. Match regex pattern
4. If api_endpoint -> gọi API lấy dữ liệu
5. Format response theo template
6. Return (answer, category, used_api)
"""

import asyncio
import json
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_system import SystemKnowledge

# API base URL - mock data cho development
API_BASE_URL = "http://localhost:8000"


@dataclass
class KBQueryResult:
    """Kết quả từ System Knowledge Base."""

    answer: str | None
    category: str | None
    used_api: bool
    matched_entry_id: int | None = None


def _extract_keywords(text: str) -> list[str]:
    """
    Extract keywords đơn giản từ câu hỏi.
    Lowercase, loại bỏ stopwords tiếng Việt/Anh phổ biến.
    """
    stopwords = {
        # Tiếng Việt
        "là", "của", "và", "có", "được", "tôi", "bạn", "mình", "vì", "với",
        "để", "trong", "này", "không", "thì", "cho", "đã", "đang", "sẽ",
        "các", "những", "một", "vào", "ra", "lên", "xuống", "làm", "sao",
        # Tiếng Anh
        "the", "a", "an", "is", "are", "was", "were", "can", "could", "will",
        "would", "should", "to", "in", "on", "at", "by", "for", "with",
        "this", "that", "these", "those", "i", "you", "he", "she", "it",
        "we", "they", "my", "your", "his", "her", "its", "our", "their",
    }

    words = re.findall(r"\w+", text.lower())
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    return keywords


def _should_include_entry(keyword: str, question_keywords: list[str]) -> bool:
    """
    Kiểm tra xem entry có nên được include không.
    Match keyword với bất kỳ word nào trong câu hỏi (fuzzy matching).
    """
    # Exact match
    if keyword in question_keywords:
        return True

    # Partial match (keyword chứa trong word hoặc ngược lại)
    for qkw in question_keywords:
        if keyword in qkw or qkw in keyword:
            return True

    # Common aliases
    aliases = {
        "enroll": ["join", "tham_gia", "vào", "đăng_ký", "dang_ky", "register", "dang", "ky", "hoc", "khoa"],
        "quiz": ["thi", "ôn", "luyện", "test", "kiểm_tra", "lam", "làm"],
        "tai lieu": ["tai_lieu", "tai", "lieu", "pdf", "document", "doc", "upload", "dang", "dong_gop"],
        "quyen": ["quyen", "quan", "permission", "right", "access", "han"],
        "giang vien": ["giang_vien", "gv", "instructor", "teacher"],
        "khoa": ["khoa", "course", "mon", "môn"],
    }

    aliases_for_keyword = aliases.get(keyword, [])
    for alias in aliases_for_keyword:
        if alias in question_keywords:
            return True

    return False


def _match_question_pattern(question: str, pattern: str) -> bool:
    """Kiểm tra xem câu hỏi có khớp với regex pattern không."""
    try:
        # Case-insensitive match
        return bool(re.search(pattern, question, re.IGNORECASE))
    except re.error:
        # Invalid regex - fallback to keyword match
        return pattern.lower() in question.lower()


def _call_mock_api(endpoint: str | None, user_id: int) -> dict | None:
    """
    Gọi API endpoint để lấy dữ liệu động.
    Hiện tại mock data cho development.
    Implement thật sau khi có API endpoints.
    """
    if not endpoint:
        return None

    # Mock data cho các endpoints phổ biến
    mock_data = {
        "/api/v1/enrollment/my-courses": {
            "courses": [
                {"id": 1, "code": "CS101", "name": "Nhập môn lập trình"},
                {"id": 2, "code": "CS201", "name": "Cấu trúc dữ liệu"},
            ]
        },
        "/api/v1/learning/can-take-quiz": {
            "can_take_quiz": True,
            "reason": "Bạn đã được thêm vào lớp học. Có thể làm quiz ngay!"
        },
        "/api/v1/learning/mastery": {
            "mastery_summary": "Bạn đã nắm vững 3/10 khái niệm. Tiếp tục luyện tập nhé!"
        },
        "/api/v1/learning/scores": {
            "scores": "Quiz: 8/10, Bài tập: 9/10"
        },
        "/api/v1/documents/accessible": {
            "documents": "Có 5 tài liệu trong lớp của bạn"
        },
    }

    # Development mode: return mock data
    return mock_data.get(endpoint)


async def _fetch_from_api(endpoint: str, user_id: int) -> dict | None:
    """
    Gọi API thật (hoặc mock) để lấy dữ liệu.
    Chạy trong thread vì httpx sync có thể block.
    """
    return await asyncio.to_thread(_call_mock_api, endpoint, user_id)


def _format_response(template: str | None, api_data: dict | None, default_answer: str) -> str:
    """Format câu trả lời với dữ liệu API."""
    if not template:
        return default_answer

    if not api_data:
        return default_answer

    try:
        # Replace placeholders với dữ liệu từ API
        formatted = template
        for key, value in api_data.items():
            placeholder = f"{{{key}}}"
            if placeholder in formatted:
                if isinstance(value, (list, dict)):
                    formatted = formatted.replace(placeholder, json.dumps(value, ensure_ascii=False))
                else:
                    formatted = formatted.replace(placeholder, str(value))
        return formatted
    except Exception:
        # Fallback to default answer if formatting fails
        return default_answer


class SystemKBQuerier:
    """
    Service để query System Knowledge Base.

    Usage:
        kb_querier = SystemKBQuerier(session)
        result = await kb_querier.query("Làm sao join lớp?", user_id=1)

        if result.answer:
            return ChatResult(
                answer=result.answer,
                category=result.category,
                ...
            )
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._cache: dict[str, list[SystemKnowledge]] = {}  # Cache by keyword

    async def _load_knowledge_by_keyword(self, keyword: str) -> list[SystemKnowledge]:
        """Load knowledge entries by keyword (with caching)."""
        if keyword in self._cache:
            return self._cache[keyword]

        result = await self.session.execute(
            select(SystemKnowledge)
            .where(SystemKnowledge.keyword == keyword)
            .where(SystemKnowledge.is_active == True)
            .order_by(SystemKnowledge.priority.asc())
        )
        entries = list(result.scalars().all())
        self._cache[keyword] = entries
        return entries

    async def query(self, question: str, user_id: int) -> KBQueryResult:
        """
        Query System Knowledge Base với câu hỏi của user.

        Args:
            question: Câu hỏi của sinh viên
            user_id: ID của user để gọi API với context

        Returns:
            KBQueryResult với câu trả lời, category, và flag used_api
        """
        # 1. Extract keywords từ câu hỏi
        keywords = _extract_keywords(question)
        if not keywords:
            return KBQueryResult(answer=None, category=None, used_api=False)

        # 2. Query all active entries and filter by keyword matching
        result = await self.session.execute(
            select(SystemKnowledge)
            .where(SystemKnowledge.is_active == True)
            .order_by(SystemKnowledge.priority.asc())
        )
        all_entries = list(result.scalars().all())

        if not all_entries:
            return KBQueryResult(answer=None, category=None, used_api=False)

        # 3. Filter entries where keyword/aliases match question keywords
        # and match regex pattern - lấy entry có priority cao nhất
        matched_entry: SystemKnowledge | None = None
        for entry in all_entries:
            # Check if entry keyword matches any question keyword
            if not _should_include_entry(entry.keyword, keywords):
                continue

            # Then check regex pattern match
            if _match_question_pattern(question, entry.question_pattern):
                if matched_entry is None or entry.priority < matched_entry.priority:
                    matched_entry = entry

        if not matched_entry:
            return KBQueryResult(answer=None, category=None, used_api=False)

        # 4. If api_endpoint -> gọi API lấy dữ liệu
        api_data = None
        if matched_entry.api_endpoint:
            api_data = await _fetch_from_api(matched_entry.api_endpoint, user_id)

        # 5. Format response theo template
        answer = _format_response(
            template=matched_entry.response_template,
            api_data=api_data,
            default_answer=matched_entry.default_answer,
        )

        # 6. Return results
        return KBQueryResult(
            answer=answer,
            category=matched_entry.category,
            used_api=api_data is not None,
            matched_entry_id=matched_entry.id,
        )


async def query_system_knowledge(
    session: AsyncSession,
    question: str,
    user_id: int,
) -> KBQueryResult:
    """
    Convenience function để query System Knowledge Base.

    Args:
        session: Database session
        question: Câu hỏi của sinh viên
        user_id: ID của user

    Returns:
        KBQueryResult với câu trả lời (None nếu không match)
    """
    querier = SystemKBQuerier(session)
    return await querier.query(question, user_id)
