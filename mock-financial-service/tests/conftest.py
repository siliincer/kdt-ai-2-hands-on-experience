"""테스트 공통 fixture — 원장 복원."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mock_financial_service import ledger
from mock_financial_service.main import app


@pytest.fixture(autouse=True)
def reset_ledger():
    yield
    ledger.reset()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
