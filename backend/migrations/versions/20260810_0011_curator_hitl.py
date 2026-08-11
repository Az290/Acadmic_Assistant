"""add document.embedding + curator_notes (Curator Agent + HITL)

Nền tảng dữ liệu cho Tác vụ #13: embedding trung bình của tài liệu
(phát hiện gần trùng lặp) + ghi chú cảnh báo tự động (injection scan,
quality gate) hiển thị cho giảng viên lúc duyệt.
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260810_0011"
down_revision = "20260810_0010"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.add_column("document", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.add_column("document", sa.Column("curator_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document", "curator_notes")
    op.drop_column("document", "embedding")
