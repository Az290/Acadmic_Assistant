"""add document.superseded_by_id (document versioning)

Cho phép đánh dấu 1 document đã bị THAY THẾ bởi bản upload mới hơn
(cùng course, cùng title), thay vì để 2 bản cùng tồn tại và bị Retrieval
trộn lẫn kết quả cũ/mới.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_0004"
down_revision = "20260808_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("superseded_by_id", sa.BigInteger(), sa.ForeignKey("document.id"), nullable=True),
    )
    # Index cho truy vấn Retrieval: loại các document đã bị thay thế
    # khỏi kết quả tìm kiếm (WHERE superseded_by_id IS NULL).
    op.create_index(
        "ix_document_superseded_by_id", "document", ["superseded_by_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_superseded_by_id", table_name="document")
    op.drop_column("document", "superseded_by_id")
