"""다은행 지원 테스트.

AC1 verify: pytest tests/test_multi_bank.py -k create -q
AC2 verify: pytest tests/test_multi_bank.py -k "transfer_success or unsupported_bank" -q
AC3 verify: pytest tests/test_multi_bank.py -k bank_name_in_response -q
"""

from financial_service.models import BANK_CATALOG, BANK_NAME

# ── helpers ───────────────────────────────────────────────────────────────────


def _create_account(client, owner: str, initial_balance: int = 0, **kwargs):
    payload: dict = {"owner": owner, "initial_balance": initial_balance, **kwargs}
    return client.post("/api/v1/accounts", json=payload)


def _transfer(
    client,
    sender: dict,
    receiver_bank_name: str,
    receiver_account_number: str,
    amount: int = 1_000,
    key: str = "k1",
):
    payload = {
        "sender_account_number": sender["account_number"],
        "receiver_bank_name": receiver_bank_name,
        "receiver_account_number": receiver_account_number,
        "amount": amount,
    }
    return client.post(
        "/api/v1/transfers", json=payload, headers={"Idempotency-Key": key}
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AC1: 계좌 생성 — 은행 지정 및 하위호환
# ═══════════════════════════════════════════════════════════════════════════════


def test_create_account_default_bank_is_kdt(client):
    """bank_name 생략 시 기본값 KDT은행으로 생성 — 하위호환."""
    r = _create_account(client, "홍길동", 50_000)
    assert r.status_code == 201
    body = r.json()
    assert body["bank_name"] == BANK_NAME  # "KDT은행"


def test_create_account_explicit_kdt_bank(client):
    """KDT은행 명시 지정 → 정상 생성."""
    r = _create_account(client, "박영희", 10_000, bank_name="KDT은행")
    assert r.status_code == 201
    assert r.json()["bank_name"] == "KDT은행"


def test_create_account_shinhan_bank(client):
    """카탈로그 내 타행(신한은행) 계좌 생성 성공."""
    r = _create_account(client, "이철수", 20_000, bank_name="신한은행")
    assert r.status_code == 201
    assert r.json()["bank_name"] == "신한은행"


def test_create_account_kb_bank(client):
    """카탈로그 내 타행(국민은행) 계좌 생성 성공."""
    r = _create_account(client, "최지영", 30_000, bank_name="국민은행")
    assert r.status_code == 201
    assert r.json()["bank_name"] == "국민은행"


def test_create_account_hana_bank(client):
    """카탈로그 내 타행(하나은행) 계좌 생성 성공."""
    r = _create_account(client, "강동원", 0, bank_name="하나은행")
    assert r.status_code == 201
    assert r.json()["bank_name"] == "하나은행"


def test_create_account_woori_bank(client):
    """카탈로그 내 타행(우리은행) 계좌 생성 성공."""
    r = _create_account(client, "손예진", 5_000, bank_name="우리은행")
    assert r.status_code == 201
    assert r.json()["bank_name"] == "우리은행"


def test_create_account_unsupported_bank_rejected(client):
    """카탈로그 밖 은행명 → 422 반환."""
    r = _create_account(client, "김민수", 1_000, bank_name="은하수은행")
    assert r.status_code == 422


def test_create_account_bank_name_in_response(client):
    """bank_name 필드가 응답 바디에 존재한다."""
    r = _create_account(client, "오서희", 5_000, bank_name="국민은행")
    assert r.status_code == 201
    body = r.json()
    assert "bank_name" in body
    assert body["bank_name"] == "국민은행"


def test_create_account_all_catalog_banks_accepted(client):
    """BANK_CATALOG 내 모든 은행으로 계좌 생성이 성공한다."""
    for i, bank in enumerate(sorted(BANK_CATALOG)):
        r = _create_account(client, f"사용자{i}", 0, bank_name=bank)
        assert r.status_code == 201, f"{bank} 계좌 생성 실패: {r.text}"
        assert r.json()["bank_name"] == bank


# ═══════════════════════════════════════════════════════════════════════════════
# AC2: 카탈로그 기반 송금 검증
# ═══════════════════════════════════════════════════════════════════════════════


def test_transfer_success_to_catalog_other_bank(client):
    """카탈로그 내 타행(신한은행) 소속 계좌로 송금 성공."""
    sender = _create_account(client, "송금자", 100_000).json()
    receiver = _create_account(client, "수취자", 0, bank_name="신한은행").json()

    r = _transfer(client, sender, "신한은행", receiver["account_number"], amount=10_000)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["receiver_bank_name"] == "신한은행"


def test_transfer_success_all_catalog_banks(client):
    """카탈로그 내 모든 은행 소속 계좌로 송금이 성공한다."""
    sender = _create_account(client, "송금자2", 1_000_000).json()
    for i, bank in enumerate(sorted(BANK_CATALOG)):
        receiver = _create_account(client, f"수취자{i}", 0, bank_name=bank).json()
        r = _transfer(
            client,
            sender,
            bank,
            receiver["account_number"],
            amount=1_000,
            key=f"k-catalog-{i}",
        )
        assert r.status_code == 200, f"{bank} 송금 실패: {r.text}"


def test_transfer_unsupported_bank_rejected(client):
    """카탈로그 밖 은행명으로 송금 시 BANK_NOT_IN_CATALOG로 거절된다."""
    sender = _create_account(client, "송금자3", 50_000).json()
    receiver = _create_account(client, "수취자3", 0).json()

    r = _transfer(client, sender, "은하수은행", receiver["account_number"])
    assert r.status_code == 422
    assert r.json()["error_code"] == "BANK_NOT_IN_CATALOG"
