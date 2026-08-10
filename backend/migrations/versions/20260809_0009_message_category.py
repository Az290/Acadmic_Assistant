"""add category + needs_retrieval columns to message

Cho phép Dashboard giảng viên thống kê "điểm mù tài liệu" (câu hỏi cần
retrieval nhưng không tìm thấy chunk liên quan nào) và câu hỏi phổ
biến theo category - theo đúng đặc tả gốc Phần 7.3.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_0009"
down_revision = "20260809_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message", sa.Column("category", sa.String(30), nullable=True))
    op.add_column("message", sa.Column("needs_retrieval", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("message", "needs_retrieval")
    op.drop_column("message", "category")
