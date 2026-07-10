"""
정보계 audit-log read endpoint — GET /analytics/accounts/{id}/audit-logs.

Verifies:
  1. 401 without X-Analytics-Key
  2. 200 with valid key, unknown account -> 404
  3. Account creation produces an ACCOUNT_CREATE entry visible via this endpoint
  4. A transfer produces entries visible to both sender and receiver
  5. audit_logs table stays DB-trigger immutable regardless of this read path
"""

ANALYTICS_KEY = "analytics-demo-key"
WRONG_KEY = "wrong-key"


def _make_account(client, owner: str, initial_balance: int = 0) -> dict:
    r = client.post(
        "/api/v1/accounts", json={"owner": owner, "initial_balance": initial_balance}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _transfer(client, sender: dict, receiver: dict, amount: int, key: str) -> dict:
    r = client.post(
        "/api/v1/transfers",
        json={
            "sender_account_number": sender["account_number"],
            "receiver_bank_name": receiver["bank_name"],
            "receiver_account_number": receiver["account_number"],
            "amount": amount,
        },
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_audit_logs_requires_key(client):
    acct = _make_account(client, "AuditNoKey", 1_000)
    r = client.get(f"/api/v1/analytics/accounts/{acct['account_id']}/audit-logs")
    assert r.status_code == 401
    assert r.json()["error_code"] == "UNAUTHORIZED"


def test_audit_logs_wrong_key(client):
    acct = _make_account(client, "AuditWrongKey", 1_000)
    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/audit-logs",
        headers={"X-Analytics-Key": WRONG_KEY},
    )
    assert r.status_code == 401


def test_audit_logs_unknown_account_404(client):
    r = client.get(
        "/api/v1/analytics/accounts/does-not-exist/audit-logs",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "ACCOUNT_NOT_FOUND"


def test_audit_logs_shows_account_create(client):
    acct = _make_account(client, "AuditCreate", 5_000)
    r = client.get(
        f"/api/v1/analytics/accounts/{acct['account_id']}/audit-logs",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    )
    assert r.status_code == 200
    logs = r.json()
    assert any(log["action"] == "ACCOUNT_CREATE" for log in logs)


def test_audit_logs_shows_transfer_for_both_sides(client):
    sender = _make_account(client, "AuditSender", 10_000)
    receiver = _make_account(client, "AuditReceiver", 0)
    _transfer(client, sender, receiver, 3_000, "audit-key-1")

    sender_logs = client.get(
        f"/api/v1/analytics/accounts/{sender['account_id']}/audit-logs",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    ).json()
    receiver_logs = client.get(
        f"/api/v1/analytics/accounts/{receiver['account_id']}/audit-logs",
        headers={"X-Analytics-Key": ANALYTICS_KEY},
    ).json()

    assert any(log["action"] == "TRANSFER" for log in sender_logs)
    assert any(log["action"] == "TRANSFER" for log in receiver_logs)


def test_audit_logs_endpoint_is_read_only(client):
    """This is a GET-only endpoint — no PATCH/PUT/DELETE registered.

    DB-trigger immutability itself is covered by test_audit_log.py; this
    just confirms the new read path adds no write surface on audit_logs.
    """
    acct = _make_account(client, "AuditReadOnly", 1_000)
    path = f"/api/v1/analytics/accounts/{acct['account_id']}/audit-logs"
    assert (
        client.get(path, headers={"X-Analytics-Key": ANALYTICS_KEY}).status_code == 200
    )
    assert (
        client.put(path, headers={"X-Analytics-Key": ANALYTICS_KEY}).status_code == 405
    )
    assert (
        client.delete(path, headers={"X-Analytics-Key": ANALYTICS_KEY}).status_code
        == 405
    )
