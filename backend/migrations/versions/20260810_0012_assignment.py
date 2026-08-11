"""add assignment, assignment_question, assignment_submission

Giao bài tập trắc nghiệm + chấm tự động (Tác vụ #13). Tái sử dụng
quiz_question đã sinh sẵn cho từng khái niệm - bài tập chỉ tham chiếu
tới chúng, không có kho câu hỏi riêng.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260810_0012"
down_revision = "20260810_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assignment",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_assignment_course_id", "assignment", ["course_id"])

    op.create_table(
        "assignment_question",
        sa.Column("assignment_id", sa.BigInteger(), sa.ForeignKey("assignment.id"), primary_key=True),
        sa.Column("quiz_question_id", sa.BigInteger(), sa.ForeignKey("quiz_question.id"), primary_key=True),
        sa.Column("ord", sa.Integer(), nullable=False),
    )

    op.create_table(
        "assignment_submission",
        sa.Column("assignment_id", sa.BigInteger(), sa.ForeignKey("assignment.id"), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), primary_key=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("assignment_submission")
    op.drop_table("assignment_question")
    op.drop_index("ix_assignment_course_id", table_name="assignment")
    op.drop_table("assignment")
