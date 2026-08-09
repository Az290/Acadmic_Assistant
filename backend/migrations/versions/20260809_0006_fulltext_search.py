"""add tsvector generated column + GIN index for BM25-style full-text search

Cột content_tsv là "generated column" - Postgres tự động tính lại giá
trị này mỗi khi content thay đổi, không cần code ứng dụng tự cập nhật
tay và không thể bị quên đồng bộ.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_0006"
down_revision = "20260809_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # "simple" thay vì "english": nội dung có cả tiếng Việt lẫn tiếng
    # Anh (thuật ngữ lập trình), cấu hình "english" sẽ áp dụng stemming
    # tiếng Anh sai lệch lên từ tiếng Việt. "simple" chỉ tách từ theo
    # khoảng trắng/dấu câu và hạ chữ thường, không suy diễn ngữ pháp -
    # an toàn cho nội dung đa ngôn ngữ, dù mất đi 1 phần lợi ích của
    # stemming thật (vd "chạy"/"chạy bộ" không tự động khớp nhau).
    op.execute(
        """
        ALTER TABLE chunk ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_chunk_content_tsv ON chunk USING GIN (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_content_tsv")
    op.execute("ALTER TABLE chunk DROP COLUMN IF EXISTS content_tsv")
