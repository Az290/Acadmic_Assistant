"""add security_log table

Nhật ký các lần Guardrail chặn nội dung - tách riêng khỏi bảng message
(lịch sử chat hiển thị cho user) để phục vụ điều tra/audit nội bộ.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_0007"
down_revision = "20260809_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("blocked_by", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("direction IN ('input','output')", name="ck_security_log_direction"),
        sa.CheckConstraint("blocked_by IN ('rules','moderation')", name="ck_security_log_blocked_by"),
    )
    # Index cho truy vấn hay dùng nhất khi điều tra: "user này bị chặn
    # bao nhiêu lần, gần đây nhất khi nào".
    op.create_index("ix_security_log_user_id", "security_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_security_log_user_id", table_name="security_log")
    op.drop_table("security_log")
