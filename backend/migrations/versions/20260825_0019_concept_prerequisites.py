"""add prerequisites column to concept

Learning Path (lộ trình học tập) cần biết khái niệm nào phải học TRƯỚC
khái niệm nào, để xác định concept đang "available" (đã đủ điều kiện
học) hay "locked" (còn thiếu tiền đề).

Lưu dạng CHUỖI JSON (vd "[2,3]") thay vì bảng quan hệ riêng: quan hệ
tiền đề chỉ được ĐỌC nguyên khối khi dựng lộ trình, không bao giờ cần
truy vấn ngược ("khái niệm nào phụ thuộc vào X") ở giai đoạn này -
thêm 1 bảng nối chỉ để phục vụ truy vấn chưa ai cần là phức tạp thừa.
Nếu sau này cần truy vấn ngược thật, đó là lúc tách bảng.

NULL = chưa khai báo tiền đề (mặc định cho mọi khái niệm đã có), được
app.learning.learning_path._parse_prerequisites() hiểu là danh sách rỗng.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260825_0019"
down_revision = "20260823_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: cột này đã được thêm tay bằng ALTER TABLE trên
    # database phát triển trước khi migration này tồn tại - không có
    # cờ đó, chạy `alembic upgrade head` trên chính máy đó sẽ vỡ.
    op.execute("ALTER TABLE concept ADD COLUMN IF NOT EXISTS prerequisites TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE concept DROP COLUMN IF EXISTS prerequisites")
