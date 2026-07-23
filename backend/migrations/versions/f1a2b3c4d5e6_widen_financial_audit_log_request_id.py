"""widen financial_audit_logs.request_id to 200 chars

Revision ID: f1a2b3c4d5e6
Revises: 317ff87f3f12
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "317ff87f3f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "financial_audit_logs",
        "request_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=200),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "financial_audit_logs",
        "request_id",
        existing_type=sa.String(length=200),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
