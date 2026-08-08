"""add refresh_token table

Migration nối tiếp 20260808_0002. Chỉ thêm 1 bảng mới, không sửa bảng
cũ - refresh token là cơ chế bổ sung cho access token JWT đã có, không
thay thế nó.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260808_0003"
down_revision = "20260808_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Index cho truy vấn hay dùng nhất: tìm mọi refresh token còn hiệu
    # lực của 1 user - dùng khi thu hồi toàn bộ phiên đăng nhập.
    op.create_index("ix_refresh_token_user_id", "refresh_token", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_token_user_id", table_name="refresh_token")
    op.drop_table("refresh_token")
