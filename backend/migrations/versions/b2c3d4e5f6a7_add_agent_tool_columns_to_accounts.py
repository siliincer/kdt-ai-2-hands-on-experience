"""add agent-tool columns to accounts (alias, account_type, is_default)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 14:00:00.000000

Stage 2: 계좌 목록(API-ACCOUNT-LIST)·기본계좌 설정에 필요한 컬럼.
alias 는 로컬 정본(D4), is_default 는 사용자당 1개 불변식(부분 유니크 인덱스).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "accounts",
        sa.Column("alias", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column("account_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # 사용자당 기본 출금 계좌는 하나만 존재(계약 20.5). 부분 유니크 인덱스로 강제.
    op.create_index(
        "ux_accounts_user_default",
        "accounts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ux_accounts_user_default", table_name="accounts")
    op.drop_column("accounts", "is_default")
    op.drop_column("accounts", "account_type")
    op.drop_column("accounts", "alias")
