"""add eval_run + eval_case_result + quiz_attempt.attempted_at

Eval Dashboard (đọc scripts/eval.py) - ghi lịch sử các lượt eval vào
DB thay vì chỉ ra file JSON cục bộ, để xem xu hướng chất lượng qua
thời gian trên trang admin.

Nhân tiện bổ sung quiz_attempt.attempted_at (cột timestamp bị thiếu từ
trước, phát hiện khi rà lại models.py cho tác vụ này) - không ảnh hưởng
logic hiện có, chỉ thêm khả năng tra thời điểm 1 lượt trả lời quiz.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260811_0016"
down_revision = "20260811_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quiz_attempt",
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "eval_run",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("git_commit_hash", sa.String(length=40), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("dataset_version", sa.String(length=50), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("category_accuracy", sa.Float(), nullable=False),
        sa.Column("avg_recall_at_k", sa.Float(), nullable=True),
        sa.Column("avg_judge_score", sa.Float(), nullable=True),
        sa.Column("judge_cases_scored", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "eval_case_result",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("eval_run_id", sa.BigInteger(), sa.ForeignKey("eval_run.id"), nullable=False),
        sa.Column("case_id", sa.String(length=100), nullable=False),
        sa.Column("expected_category", sa.String(length=50), nullable=False),
        sa.Column("actual_category", sa.String(length=50), nullable=True),
        sa.Column("category_match", sa.Boolean(), nullable=True),
        sa.Column("recall_at_k", sa.Float(), nullable=True),
        sa.Column("judge_score", sa.Integer(), nullable=True),
        sa.Column("judge_reasoning", sa.Text(), nullable=True),
        sa.Column("answer_preview", sa.Text(), nullable=True),
        sa.Column("latency_s", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_eval_case_result_eval_run_id", "eval_case_result", ["eval_run_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_case_result_eval_run_id", table_name="eval_case_result")
    op.drop_table("eval_case_result")
    op.drop_table("eval_run")
    op.drop_column("quiz_attempt", "attempted_at")
