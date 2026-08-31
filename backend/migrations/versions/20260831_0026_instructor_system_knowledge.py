"""scope system knowledge by effective role

Revision ID: 20260831_0026
Revises: 20260831_0025
"""
from alembic import op
import sqlalchemy as sa

revision = "20260831_0026"
down_revision = "20260831_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("system_knowledge", sa.Column(
        "audience_scope", sa.String(length=20), nullable=False, server_default="ALL"
    ))
    op.create_check_constraint(
        "ck_system_knowledge_audience", "system_knowledge",
        "audience_scope IN ('ALL','STUDENT','INSTRUCTOR','ADMIN')",
    )
    op.create_index("ix_system_knowledge_audience", "system_knowledge", ["audience_scope"])
    op.execute("""
        INSERT INTO system_knowledge
            (keyword, question_pattern, default_answer, category, audience_scope, priority, is_active)
        VALUES
            ('upload', '(tải|tai|upload).*(tài liệu|tai lieu|pdf)',
             'Giảng viên có thể tải tài liệu trực tiếp vào lớp mình sở hữu. Hãy kiểm tra lớp đã chọn, PDF tối đa 50MB và trạng thái xử lý. Tài liệu do chính giảng viên tải lên không phải chờ một giảng viên khác duyệt.',
             'INSTRUCTOR_DOCUMENT_SUPPORT', 'INSTRUCTOR', 1, true),
            ('thống kê', '(thống kê|thong ke|sinh viên yếu|sinh vien yeu|lộ trình giảng dạy|lo trinh giang day)',
             'Hãy chọn lớp cần phân tích. Nova sẽ dùng mastery và kết quả bài tập chính thức để nêu nhóm cần hỗ trợ, nhóm đang làm tốt, khoảng trống khái niệm và gợi ý lộ trình; không đọc hội thoại riêng của sinh viên.',
             'INSTRUCTOR_TEACHING_SUPPORT', 'INSTRUCTOR', 1, true)
    """)


def downgrade() -> None:
    op.execute("DELETE FROM system_knowledge WHERE category IN ('INSTRUCTOR_DOCUMENT_SUPPORT','INSTRUCTOR_TEACHING_SUPPORT')")
    op.drop_index("ix_system_knowledge_audience", table_name="system_knowledge")
    op.drop_constraint("ck_system_knowledge_audience", "system_knowledge", type_="check")
    op.drop_column("system_knowledge", "audience_scope")
