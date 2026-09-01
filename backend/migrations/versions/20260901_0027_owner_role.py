"""add private owner role

Revision ID: 20260901_0027
Revises: 20260831_0026
"""
from alembic import op


revision = "20260901_0027"
down_revision = "20260831_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_app_user_role", "app_user", type_="check")
    op.create_check_constraint(
        "ck_app_user_role",
        "app_user",
        "role IN ('STUDENT','INSTRUCTOR','ADMIN','OWNER')",
    )


def downgrade() -> None:
    op.execute("UPDATE app_user SET role = 'ADMIN' WHERE role = 'OWNER'")
    op.drop_constraint("ck_app_user_role", "app_user", type_="check")
    op.create_check_constraint(
        "ck_app_user_role",
        "app_user",
        "role IN ('STUDENT','INSTRUCTOR','ADMIN')",
    )

