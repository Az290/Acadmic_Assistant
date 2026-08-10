"""add embedding column to concept

Cho phép xác định "câu hỏi thuộc khái niệm nào" bằng so khớp ngữ nghĩa
NGAY TRONG BỘ NHỚ (không gọi thêm API, không thêm độ trễ cho người
dùng) - vector tên khái niệm tính 1 lần lúc tạo, vector câu hỏi tái
dùng từ Hybrid Search.
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260810_0010"
down_revision = "20260809_0009"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.add_column("concept", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))


def downgrade() -> None:
    op.drop_column("concept", "embedding")
