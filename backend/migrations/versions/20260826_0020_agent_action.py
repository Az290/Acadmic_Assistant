"""add pending_action column to message + agent_action_log table

Nova function-calling (category ACTION_REQUEST, xem
app/academic_agent/tool_executor.py): cần 2 việc mới ở tầng dữ liệu.

1. message.pending_action - hành động Nova ĐỀ XUẤT nhưng CHƯA thực thi,
   đang chờ người dùng xác nhận ở lượt chat tiếp theo. Đây là cơ chế an
   toàn cốt lõi: Nova không bao giờ ghi dữ liệu ngay trong lượt LLM chọn
   tool, luôn phải qua bước xác nhận riêng biệt.

2. agent_action_log - nhật ký MỌI hành động Nova THỰC SỰ thực thi thay
   người dùng (tách khỏi security_log vì ý nghĩa khác hẳn - security_log
   ghi nội dung BỊ CHẶN, bảng này ghi hành động ĐÃ CHẠY, thành công hay
   thất bại vì lý do nghiệp vụ).
"""

from alembic import op
import sqlalchemy as sa

revision = "20260826_0020"
down_revision = "20260825_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE message ADD COLUMN IF NOT EXISTS pending_action TEXT")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_action_log (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES app_user(id),
            conversation_id BIGINT NOT NULL REFERENCES conversation(id),
            tool_name VARCHAR(50) NOT NULL,
            arguments TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            result_summary TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_action_log")
    op.execute("ALTER TABLE message DROP COLUMN IF EXISTS pending_action")
