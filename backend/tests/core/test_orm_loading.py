"""ORM 로딩 전략 회귀 가드 (R4).

agent-tools 모델의 스칼라 관계는 서비스가 컬럼(user_id 등)만 쓰므로 자동 로딩하지
않는다(lazy="raise"). 누군가 실수로 selectin 으로 되돌리면(hot path resolve_context 마다
+SELECT 부활) 이 테스트가 잡는다.
"""

from sqlalchemy import inspect

from backend.models import (
    AuthContext,
    Confirmation,
    ExecutionContext,
    FinancialAuditLog,
    RecipientCandidate,
    TransactionQueryContext,
)


def _lazy(model, relationship_name: str) -> str:
    return inspect(model).relationships[relationship_name].lazy


def test_agent_tools_scalar_relationships_do_not_autoload():
    expected = {
        (ExecutionContext, "user"),
        (ExecutionContext, "chat_session"),
        (Confirmation, "user"),
        (Confirmation, "execution_context"),
        (AuthContext, "user"),
        (AuthContext, "confirmation"),
        (FinancialAuditLog, "user"),
        (TransactionQueryContext, "user"),
        (RecipientCandidate, "user"),
    }
    for model, name in expected:
        assert _lazy(model, name) == "raise", f"{model.__name__}.{name} 가 자동 로딩됨"
