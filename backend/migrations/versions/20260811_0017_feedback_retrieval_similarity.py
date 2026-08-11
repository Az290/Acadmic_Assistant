"""add message_feedback + message.retrieval_similarity

Feedback 👍/👎 của sinh viên cho từng câu trả lời, và độ khớp tài liệu
thật (cosine similarity cao nhất của lượt tìm kiếm) - 2 nguồn dữ liệu
cho trang "Câu hỏi phổ biến" của giảng viên.

retrieval_similarity KHÔNG đặt tên là "confidence" có chủ ý - xem
docstring cột này trong app/db/models.py::Message.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260811_0017"
down_revision = "20260811_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message", sa.Column("retrieval_similarity", sa.Float(), nullable=True))

    op.create_table(
        "message_feedback",
        sa.Column("message_id", sa.BigInteger(), sa.ForeignKey("message.id"), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), primary_key=True),
        sa.Column("is_positive", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("message_feedback")
    op.drop_column("message", "retrieval_similarity")
