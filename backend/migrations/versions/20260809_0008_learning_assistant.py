"""add concept, student_mastery, quiz_question, quiz_attempt tables

Nền tảng dữ liệu cho Learning Assistant (Tác vụ #10): concept do giảng
viên tự tạo tay, mastery tính bằng heuristic đếm streak (không phải
BKT thật - cần đủ dữ liệu tương tác mới fit tham số có ý nghĩa), quiz
sinh bằng LLM rồi cache lại để tái dùng.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_0008"
down_revision = "20260809_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("complexity", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("complexity BETWEEN 1 AND 5", name="ck_concept_complexity"),
    )
    op.create_index("ix_concept_course_id", "concept", ["course_id"])

    op.create_table(
        "student_mastery",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), primary_key=True),
        sa.Column("concept_id", sa.BigInteger(), sa.ForeignKey("concept.id"), primary_key=True),
        sa.Column("streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_obs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mastered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "quiz_question",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("concept_id", sa.BigInteger(), sa.ForeignKey("concept.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", sa.Text(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quiz_question_concept_id", "quiz_question", ["concept_id"])

    op.create_table(
        "quiz_attempt",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("quiz_question_id", sa.BigInteger(), sa.ForeignKey("quiz_question.id"), nullable=False),
        sa.Column("selected_index", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quiz_attempt_user_id", "quiz_attempt", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_quiz_attempt_user_id", table_name="quiz_attempt")
    op.drop_table("quiz_attempt")
    op.drop_index("ix_quiz_question_concept_id", table_name="quiz_question")
    op.drop_table("quiz_question")
    op.drop_table("student_mastery")
    op.drop_index("ix_concept_course_id", table_name="concept")
    op.drop_table("concept")
