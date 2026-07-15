"""create execution_contexts table

Revision ID: a1b2c3d4e5f6
Revises: c1d2e3f4a5b6
Create Date: 2026-07-15 13:00:00.000000

Agent Tool API(/api/v1/agent-tools/*)의 사용자·실행 권한 Context. Backend 가 발급하고
X-Execution-Context-Id 로 사용자를 결정한다(계약 5장). Stage 1 기반 스키마.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # create_type=False: 타입 생성은 아래 .create(checkfirst=True) 로만 수행한다.
    # (기본값이면 create_table 의 컬럼이 CREATE TYPE 를 재발행해 DuplicateObject 발생)
    execution_context_status = postgresql.ENUM(
        "ACTIVE",
        "EXPIRED",
        "CANCELLED",
        "COMPLETED",
        name="execution_context_status",
        create_type=False,
    )
    execution_context_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "execution_contexts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "chat_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id"),
            nullable=False,
        ),
        sa.Column("agent_thread_id", sa.String(length=64), nullable=True),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            execution_context_status,
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Asia/Seoul",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_execution_contexts_chat_session_id",
        "execution_contexts",
        ["chat_session_id"],
    )
    op.create_index(
        "ix_execution_contexts_agent_thread_id",
        "execution_contexts",
        ["agent_thread_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_execution_contexts_agent_thread_id", table_name="execution_contexts"
    )
    op.drop_index(
        "ix_execution_contexts_chat_session_id", table_name="execution_contexts"
    )
    op.drop_table("execution_contexts")
    postgresql.ENUM(name="execution_context_status").drop(
        op.get_bind(), checkfirst=True
    )
