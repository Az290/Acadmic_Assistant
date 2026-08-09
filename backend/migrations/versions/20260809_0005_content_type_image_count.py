"""add chunk.content_type + document.image_count

Hai cột hỗ trợ Ingestion Pipeline xử lý tốt hơn với bảng biểu và ảnh
trong PDF: content_type phân biệt chunk là văn bản thường hay bảng
(markdown table), image_count đếm số ảnh chưa xử lý được trong tài liệu.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_0005"
down_revision = "20260809_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunk",
        sa.Column("content_type", sa.String(20), nullable=False, server_default="TEXT"),
    )
    op.create_check_constraint(
        "ck_chunk_content_type", "chunk", "content_type IN ('TEXT','TABLE')"
    )

    op.add_column(
        "document",
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("document", "image_count")
    op.drop_constraint("ck_chunk_content_type", "chunk", type_="check")
    op.drop_column("chunk", "content_type")
