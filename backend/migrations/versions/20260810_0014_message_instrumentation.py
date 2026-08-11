"""add message.token_usage + message.latency_ms

Đo lường vận hành tự động cho mỗi câu trả lời - nền tảng cho Cost
Dashboard và Pipeline Visualization (thay vì phải đo thủ công từng
lần như trước đây).
"""

from alembic import op
import sqlalchemy as sa

revision = "20260810_0014"
down_revision = "20260810_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message", sa.Column("token_usage", sa.Text(), nullable=True))
    op.add_column("message", sa.Column("latency_ms", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("message", "latency_ms")
    op.drop_column("message", "token_usage")
