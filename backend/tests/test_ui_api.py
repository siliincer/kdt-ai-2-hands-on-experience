from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.schemas.ui import BalanceData
from backend.services.mock_agent_driver import _match_component
from backend.services.ui_service import get_balance_view


def test_match_component_detects_balance_intent():
    assert _match_component("내 잔액 알려줘") == "balance"
    assert _match_component("총 자산 얼마야") == "balance"
    assert _match_component("송금하고 싶어") is None


@pytest.mark.asyncio
async def test_get_balance_view_returns_balance_data():
    data = await get_balance_view(uuid4())
    assert isinstance(data, BalanceData)
    assert data.total == sum(a.balance for a in data.accounts)
    assert len(data.accounts) >= 1


def test_ui_balance_requires_auth(client: TestClient):
    response = client.get("/api/v1/ui/balance")
    assert response.status_code in (401, 403)
