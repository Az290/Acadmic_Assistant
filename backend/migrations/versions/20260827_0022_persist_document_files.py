"""persist original document files in PostgreSQL"""

from alembic import op
import sqlalchemy as sa

revision = "20260827_0022"
down_revision = "20260827_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document", sa.Column("original_file", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("document", "original_file")
