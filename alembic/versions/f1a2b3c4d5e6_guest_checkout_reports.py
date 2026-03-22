"""Guest checkout: nullable report.user_id, assessment.guest_email

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
"""
from typing import Union, Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("guest_email", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.drop_column("guest_email")
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
