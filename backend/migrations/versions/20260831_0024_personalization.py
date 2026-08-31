"""add explicit learning preferences and scoped conversation memory"""

from alembic import op

revision = "20260831_0024"
down_revision = "20260827_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_learning_preference (
            user_id BIGINT PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
            preferred_language VARCHAR(10) NOT NULL DEFAULT 'auto',
            explanation_depth VARCHAR(20) NOT NULL DEFAULT 'auto',
            response_length VARCHAR(20) NOT NULL DEFAULT 'auto',
            example_style VARCHAR(20) NOT NULL DEFAULT 'auto',
            source VARCHAR(20) NOT NULL DEFAULT 'explicit',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_learning_preference_language CHECK (preferred_language IN ('auto','vi','en')),
            CONSTRAINT ck_learning_preference_depth CHECK (explanation_depth IN ('auto','beginner','intermediate','advanced')),
            CONSTRAINT ck_learning_preference_length CHECK (response_length IN ('auto','short','medium','detailed')),
            CONSTRAINT ck_learning_preference_example_style CHECK (example_style IN ('auto','code','analogy','step_by_step')),
            CONSTRAINT ck_learning_preference_source CHECK (source IN ('explicit','inferred'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE conversation_memory (
            conversation_id BIGINT PRIMARY KEY REFERENCES conversation(id) ON DELETE CASCADE,
            summary TEXT NOT NULL DEFAULT '',
            covered_concepts TEXT NOT NULL DEFAULT '[]',
            open_questions TEXT NOT NULL DEFAULT '[]',
            last_summarized_message_id BIGINT REFERENCES message(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_memory")
    op.execute("DROP TABLE IF EXISTS user_learning_preference")
