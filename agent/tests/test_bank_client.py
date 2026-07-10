"""BankClient 계약 테스트.

- LocalBankClient: 인메모리 원장 동작 + live 참조 계약 (identity)
- HttpBankClient: httpx.MockTransport로 시트 API Spec 계약(메서드/경로/
  파라미터/바디) 검증 — 실제 네트워크 없음
- 팩토리: BANK_CLIENT 환경변수 스위치
"""

from __future__ import annotations

import json

import httpx
import pytest

from agent.bank_client import (
    BankClientError,
    HttpBankClient,
    LocalBankClient,
    get_bank_client,
)
from agent.data.mock_bank import AUDIT_LOG, MOCK_ACCOUNTS

# ── LocalBankClient ───────────────────────────────────────────────────────────


def test_local_get_accounts_returns_live_references():
    """복사가 아니라 원장의 live dict를 그대로 반환해야 한다.

    transfer의 in-place 잔액 차감과 _live_account 재조회 의미론이
    이 참조 공유에 의존한다 — 복사로 바꾸면 조용히 깨진다.
    """
    client = LocalBankClient()
    accounts = client.get_accounts("user_001")
    assert accounts[0] is MOCK_ACCOUNTS["user_001"][0]

    filtered = client.get_accounts("user_001", account_id="acc_002")
    assert len(filtered) == 1
    assert filtered[0] is MOCK_ACCOUNTS["user_001"][1]


def test_local_get_recipients_with_name_filter():
    client = LocalBankClient()
    assert len(client.get_recipients("user_001")) == 2
    matched = client.get_recipients("user_001", recipient_name="김철수")
    assert len(matched) == 1
    assert matched[0]["recipient_id"] == "rec_001"


def test_local_transfer_deducts_and_errors():
    client = LocalBankClient()
    before = MOCK_ACCOUNTS["user_001"][0]["balance"]

    result = client.transfer("user_001", "acc_001", "rec_001", 50_000)
    assert result["status"] == "completed"
    assert result["transaction_id"].startswith("txn_")
    assert MOCK_ACCOUNTS["user_001"][0]["balance"] == before - 50_000

    with pytest.raises(BankClientError):
        client.transfer("user_001", "acc_없음", "rec_001", 1)
    with pytest.raises(BankClientError):
        client.transfer("user_001", "acc_001", "rec_없음", 1)
    with pytest.raises(BankClientError):
        client.transfer("user_001", "acc_002", "rec_001", 999_999_999)


def test_local_post_audit_log_appends():
    client = LocalBankClient()
    result = client.post_audit_log("test_event", "wf_x", "tool_x", {"k": "v"})
    assert result["log_id"].startswith("local_log_")
    assert AUDIT_LOG[-1]["event_type"] == "test_event"


# ── HttpBankClient (MockTransport 계약 검증) ─────────────────────────────────


def _capture_client(responder) -> tuple[HttpBankClient, list[httpx.Request]]:
    """요청을 기록하면서 responder(request)로 응답하는 클라이언트를 만든다."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return responder(request)

    client = HttpBankClient(
        base_url="http://bank.test", transport=httpx.MockTransport(handler)
    )
    return client, captured


def test_http_get_accounts_contract():
    client, captured = _capture_client(
        lambda req: httpx.Response(200, json={"accounts": [{"account_id": "a"}]})
    )
    accounts = client.get_accounts("user_001", account_id="acc_001")

    request = captured[0]
    assert request.method == "GET"
    assert request.url.path == "/api/accounts/user_001"
    assert request.url.params["account_id"] == "acc_001"
    assert accounts == [{"account_id": "a"}]


def test_http_get_accounts_404_translates_to_empty():
    client, _ = _capture_client(lambda req: httpx.Response(404))
    assert client.get_accounts("없는사용자") == []


def test_http_get_accounts_500_raises():
    client, _ = _capture_client(lambda req: httpx.Response(500))
    with pytest.raises(BankClientError):
        client.get_accounts("user_001")


def test_http_get_recipients_contract():
    client, captured = _capture_client(
        lambda req: httpx.Response(200, json={"recipient_candidates": []})
    )
    client.get_recipients("user_001", recipient_name="김철수")

    request = captured[0]
    assert request.url.path == "/api/recipients"
    assert request.url.params["user_id"] == "user_001"
    assert request.url.params["recipient_name"] == "김철수"


def test_http_transfer_contract():
    client, captured = _capture_client(
        lambda req: httpx.Response(
            200, json={"transaction_id": "txn_abc", "status": "completed"}
        )
    )
    result = client.transfer("user_001", "acc_001", "rec_001", 50_000, memo="점심")

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/api/transactions/transfer-external"
    body = json.loads(request.content)
    assert body == {
        "user_id": "user_001",
        "from_account_id": "acc_001",
        "to_recipient_id": "rec_001",
        "amount": 50_000,
        "memo": "점심",
    }
    assert result["transaction_id"] == "txn_abc"


def test_http_transfer_409_raises():
    client, _ = _capture_client(lambda req: httpx.Response(409))
    with pytest.raises(BankClientError):
        client.transfer("user_001", "acc_001", "rec_001", 999_999_999)


def test_http_post_audit_log_contract():
    client, captured = _capture_client(
        lambda req: httpx.Response(200, json={"log_id": "srv_log_0001"})
    )
    result = client.post_audit_log("workflow_completed", "wf_x", "tool_x", {})

    request = captured[0]
    assert request.url.path == "/api/audit-logs"
    assert json.loads(request.content)["event_type"] == "workflow_completed"
    assert result["log_id"] == "srv_log_0001"


def test_http_connection_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("연결 거부")

    client = HttpBankClient(
        base_url="http://bank.test", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(BankClientError):
        client.get_accounts("user_001")


# ── 팩토리 스위치 ─────────────────────────────────────────────────────────────


def test_factory_defaults_to_local():
    get_bank_client.cache_clear()
    assert isinstance(get_bank_client(), LocalBankClient)


def test_factory_switches_to_http(monkeypatch):
    monkeypatch.setenv("BANK_CLIENT", "http")
    monkeypatch.setenv("MOCK_FINANCIAL_SERVICE_URL", "http://bank.test")
    get_bank_client.cache_clear()
    client = get_bank_client()
    assert isinstance(client, HttpBankClient)
    get_bank_client.cache_clear()  # 후속 테스트 오염 방지 (fixture도 정리함)
