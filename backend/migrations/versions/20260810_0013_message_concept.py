"""add message.concept_id (Gap Analysis theo chủ đề)

Cho phép trả lời "sinh viên hỏi nhiều về chủ đề nào mà tài liệu không
đáp ứng được" - cụ thể hơn tỷ lệ % chung chung đã có.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260810_0013"
down_revision = "20260810_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "message",
        sa.Column("concept_id", sa.BigInteger(), sa.ForeignKey("concept.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("message", "concept_id")
