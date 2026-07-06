"""원장 API 계약 테스트 (시트 API Spec 탭 기준)."""

from __future__ import annotations


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_get_accounts(client):
    response = client.get("/api/accounts/user_001")
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user_001"
    assert len(body["accounts"]) == 2
    assert {"account_id", "account_name", "balance", "currency"} <= set(
        body["accounts"][0]
    )


def test_get_accounts_unknown_user_404(client):
    assert client.get("/api/accounts/없는사용자").status_code == 404


def test_get_accounts_filter(client):
    response = client.get("/api/accounts/user_001", params={"account_id": "acc_002"})
    accounts = response.json()["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["account_name"] == "생활비통장"

    missing = client.get("/api/accounts/user_001", params={"account_id": "acc_x"})
    assert missing.status_code == 404


def test_get_recipients_search_semantics(client):
    all_recipients = client.get(
        "/api/recipients", params={"user_id": "user_001"}
    ).json()["recipient_candidates"]
    assert len(all_recipients) == 2

    matched = client.get(
        "/api/recipients",
        params={"user_id": "user_001", "recipient_name": "김철수"},
    ).json()["recipient_candidates"]
    assert len(matched) == 1

    # 검색형 — 무매칭/미등록 사용자도 200 + 빈 목록
    empty = client.get("/api/recipients", params={"user_id": "없는사용자"}).json()[
        "recipient_candidates"
    ]
    assert empty == []


def test_transfer_deducts_ledger(client):
    before = client.get("/api/accounts/user_001").json()["accounts"][0]["balance"]

    response = client.post(
        "/api/transactions/transfer-external",
        json={
            "user_id": "user_001",
            "from_account_id": "acc_001",
            "to_recipient_id": "rec_001",
            "amount": 50_000,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["transaction_id"].startswith("txn_")

    after = client.get("/api/accounts/user_001").json()["accounts"][0]["balance"]
    assert after == before - 50_000


def test_transfer_error_semantics(client):
    base = {
        "user_id": "user_001",
        "from_account_id": "acc_001",
        "to_recipient_id": "rec_001",
        "amount": 1_000,
    }
    # 계좌 없음 -> 404
    r = client.post(
        "/api/transactions/transfer-external",
        json={**base, "from_account_id": "acc_x"},
    )
    assert r.status_code == 404
    # 수취인 없음 -> 404
    r = client.post(
        "/api/transactions/transfer-external",
        json={**base, "to_recipient_id": "rec_x"},
    )
    assert r.status_code == 404
    # 잔액 부족 -> 409
    r = client.post(
        "/api/transactions/transfer-external",
        json={**base, "amount": 999_999_999},
    )
    assert r.status_code == 409
    # 금액 0 이하 -> 422
    r = client.post("/api/transactions/transfer-external", json={**base, "amount": 0})
    assert r.status_code == 422


def test_audit_logs(client):
    response = client.post(
        "/api/audit-logs",
        json={"event_type": "workflow_completed", "workflow_id": "wf_x"},
    )
    assert response.status_code == 200
    assert response.json()["log_id"] == "srv_log_0001"
