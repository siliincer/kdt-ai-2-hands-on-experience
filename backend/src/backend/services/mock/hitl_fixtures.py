"""HITL(need_input·결과) 목 픽스처 (mock 분리 원칙, FE_coding).

wf_balance_inquiry 등 UI-HITL 워크플로우를 실 Agent 없이 재현하기 위한 계좌·잔액 목이다.
스키마는 agent-ui-hitl-contract.md 3.3(account_card_list)·4.2(balance_result)를 따른다.

TODO(BE): 실 Agent 연동 시 이 파일과 mock 시퀀스를 제거한다(agent-tools API로 대체).
"""

# UI 계약 식별자(계약 5.3).
UI_BALANCE_ACCOUNT_SELECTION = "UI-BALANCE-ACCOUNT-SELECTION"

# account_card_list 표시용 계좌 후보(계약 3.3). 전체 계좌번호 없이 마스킹본만 둔다.
BALANCE_ACCOUNTS = [
    {
        "account_id": "acc_001",
        "bank_name": "신한은행",
        "account_alias": "입출금통장",
        "account_type": "checking",
        "masked_account_number": "110-***-4200",
        "currency": "KRW",
        "is_default": True,
    },
    {
        "account_id": "acc_002",
        "bank_name": "카카오뱅크",
        "account_alias": "세이프박스",
        "account_type": "savings",
        "masked_account_number": "3333-**-1234",
        "currency": "KRW",
        "is_default": False,
    },
]

# 잔액·출금가능금액(계약 4.2). available_amount 는 hold 개념 없이 balance 근사(D7).
_BALANCE_BY_ACCOUNT = {
    "acc_001": {"balance": 8_200_000, "available_amount": 8_180_000},
    "acc_002": {"balance": 4_650_000, "available_amount": 4_650_000},
}


def build_balance_result(account_ids: list[str]) -> dict:
    """선택된 계좌들의 balance_result payload 를 구성한다(계약 4.2 인라인)."""
    accounts = []
    for account in BALANCE_ACCOUNTS:
        if account["account_id"] not in account_ids:
            continue
        balance = _BALANCE_BY_ACCOUNT.get(account["account_id"], {})
        accounts.append(
            {
                "account_id": account["account_id"],
                "account_alias": account["account_alias"],
                "masked_account_number": account["masked_account_number"],
                "balance": balance.get("balance", 0),
                "available_amount": balance.get("available_amount", 0),
                "currency": account["currency"],
            }
        )
    return {"accounts": accounts}


# ── wf_set_account_alias (계약 5.7) ──────────────────────────────────────────
# UI 계약 식별자.
UI_ACCOUNT_ALIAS_INPUT = "UI-ACCOUNT-ALIAS-INPUT"
UI_ACCOUNT_ALIAS_CONFIRMATION = "UI-ACCOUNT-ALIAS-CONFIRMATION"

# 별칭 변경 대상 계좌(계약 21.4: 식별용 마스킹 정보만). 계좌 선택 단계는 Slice 1 에서
# account_card_list 로 이미 검증했으므로, 별칭 흐름은 기본 계좌를 고정해 둔다.
ALIAS_TARGET_ACCOUNT = {
    "account_id": "acc_001",
    "bank_name": "신한은행",
    "masked_account_number": "110-***-4200",
}


def build_alias_confirm_view(alias: str) -> dict:
    """계좌 별칭 변경 confirm_modal payload(계약 3.7·21.4)."""
    return {
        "purpose": "account_alias",
        "title": "계좌 별칭을 변경할까요?",
        "account": ALIAS_TARGET_ACCOUNT,
        "alias": alias,
        "allowed_change_targets": ["alias"],
        "actions": ["approve", "modify", "cancel"],
    }


def build_alias_setting_result(alias: str | None, completed_at: str) -> dict:
    """계좌 별칭 변경 setting_result payload(계약 4.6)."""
    return {
        "purpose": "account_alias",
        "outcome": "completed",
        "account": {
            "account_id": ALIAS_TARGET_ACCOUNT["account_id"],
            "masked_account_number": ALIAS_TARGET_ACCOUNT["masked_account_number"],
        },
        "alias": alias,
        "completed_at": completed_at,
    }
