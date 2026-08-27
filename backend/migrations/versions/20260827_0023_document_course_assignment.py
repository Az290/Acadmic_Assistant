"""allow student contributions to be assigned to courses during review"""

from alembic import op

revision = "20260827_0023"
down_revision = "20260827_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document ALTER COLUMN course_id DROP NOT NULL")
    op.execute("ALTER TABLE chunk ALTER COLUMN course_id DROP NOT NULL")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_course (
            document_id BIGINT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
            course_id BIGINT NOT NULL REFERENCES course(id) ON DELETE CASCADE,
            PRIMARY KEY (document_id, course_id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO document_course (document_id, course_id)
        SELECT id, course_id FROM document WHERE course_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_course_course ON document_course (course_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_course")
    op.execute("DELETE FROM chunk WHERE course_id IS NULL")
    op.execute("DELETE FROM document WHERE course_id IS NULL")
    op.execute("ALTER TABLE chunk ALTER COLUMN course_id SET NOT NULL")
    op.execute("ALTER TABLE document ALTER COLUMN course_id SET NOT NULL")
