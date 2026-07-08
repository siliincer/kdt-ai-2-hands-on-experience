"""UI Data API (BFF) 응답 스키마.

Agent 는 `component` SSE 시그널만 보내고(ADR-002), FE 가 이 엔드포인트로 카드 데이터를
조회한다. 현재는 목 픽스처, 향후 postgres/redis/mock-financial-service 조회로 교체.
스키마는 backend/docs/agent_ui_event_spec.md §4b 와 일치한다.
"""

from pydantic import BaseModel, Field


class AccountSummary(BaseModel):
    id: int
    bank: str
    alias: str
    tail: str
    balance: int
    color: str


class BalanceData(BaseModel):
    """GET /api/v1/ui/balance"""

    total: int = Field(description="총 자산(원)")
    accounts: list[AccountSummary]
