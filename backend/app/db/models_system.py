"""
Models cho System Knowledge Base - cho phép Agent trả lời câu hỏi về
CÁCH HỆ THỐNG hoạt động (không phải nội dung môn học).

Ví dụ: "Làm sao join lớp?", "Tôi đang học khóa nào?", "Tại sao tôi
không làm quiz được?", "Làm sao upload tài liệu?"

KHÁC với system_knowledge.py (hardcoded string): đây là database-based
cho phép Admin quản lý nội dung động qua CRUD API.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Lớp gốc mà mọi bảng kế thừa."""

    pass


class SystemKnowledge(Base):
    """
    Kiến thức về hệ thống Academic Assistant - lưu trong database thay
    vì hardcoded, cho phép Admin quản lý nội dung động.

    keyword: từ khóa để match nhanh (VD: "enroll", "join", "quiz")
    question_pattern: regex pattern để match câu hỏi cụ thể
    default_answer: câu trả lời mặc định (khi không gọi API)
    category: phân loại kiến thức (ENROLLMENT, QUIZ, DOCUMENT, PERMISSION...)
    api_endpoint: endpoint để lấy dữ liệu động (mock hiện tại, implement sau)
    response_template: template để format câu trả lời với dữ liệu API
    priority: thứ tự ưu tiên khi match (số càng nhỏ = ưu tiên cao)
    is_active: có đang active không
    """

    __tablename__ = "system_knowledge"
    __table_args__ = (
        CheckConstraint("audience_scope IN ('ALL','STUDENT','INSTRUCTOR','ADMIN')", name="ck_system_knowledge_audience"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    question_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    default_answer: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    audience_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="ALL")
    api_endpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    response_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
