"""store exact answers for each assignment submission"""

from alembic import op

revision = "20260827_0021"
down_revision = "20260826_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_submission_answer (
            assignment_id BIGINT NOT NULL REFERENCES assignment(id),
            user_id BIGINT NOT NULL REFERENCES app_user(id),
            quiz_question_id BIGINT NOT NULL REFERENCES quiz_question(id),
            concept_name VARCHAR(300) NOT NULL,
            question TEXT NOT NULL,
            options TEXT NOT NULL,
            selected_index INTEGER,
            correct_index INTEGER NOT NULL,
            is_correct BOOLEAN NOT NULL,
            explanation TEXT NOT NULL,
            PRIMARY KEY (assignment_id, user_id, quiz_question_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assignment_answer_user_assignment "
        "ON assignment_submission_answer (user_id, assignment_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS assignment_submission_answer")
