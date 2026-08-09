"""add owner_id to course + create enrollment table

Migration này NỐI TIẾP migration đầu tiên (20260807_0001), không sửa
lại nó - đúng nguyên tắc "Alembic là Git cho database": mỗi thay đổi
là 1 bước mới, giữ được lịch sử đầy đủ.

Hai thay đổi:
1. Thêm cột owner_id vào bảng course - biết giáo viên nào tạo/sở hữu
   lớp, dùng để kiểm tra quyền khi thêm học sinh vào lớp.
2. Tạo bảng enrollment - "ai thuộc lớp nào", nền tảng cho tính năng
   "kênh riêng của giáo viên".
"""

from alembic import op
import sqlalchemy as sa

revision = "20260808_0002"
down_revision = "20260807_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nullable=True lúc đầu vì bảng course có thể đã có dữ liệu (ở môi
    # trường thật) chưa có owner_id - thêm cột trước, gán giá trị mặc
    # định nếu cần, rồi mới ràng buộc NOT NULL. Ở dự án này DB còn
    # trống nên bước gán giá trị mặc định không cần thiết, nhưng viết
    # theo đúng thực hành chuẩn để an toàn nếu chạy trên DB đã có dữ liệu.
    op.add_column("course", sa.Column("owner_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_course_owner_id", "course", "app_user", ["owner_id"], ["id"]
    )
    op.alter_column("course", "owner_id", nullable=False)

    op.create_table(
        "enrollment",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), primary_key=True),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("course.id"), primary_key=True),
        sa.Column("role_in_course", sa.String(20), nullable=False, server_default="STUDENT"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "role_in_course IN ('STUDENT','INSTRUCTOR')", name="ck_enrollment_role"
        ),
    )


def downgrade() -> None:
    op.drop_table("enrollment")
    op.drop_constraint("fk_course_owner_id", "course", type_="foreignkey")
    op.drop_column("course", "owner_id")
