"""add document.rejection_reason

Tách lý do từ chối (text tự do, do giảng viên viết) khỏi curator_notes
(giờ là JSON có schema cố định, do Curator Agent tạo tự động) - tránh
2 nguồn dữ liệu khác cấu trúc bị nối chung vào 1 cột.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260811_0015"
down_revision = "20260810_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document", "rejection_reason")
