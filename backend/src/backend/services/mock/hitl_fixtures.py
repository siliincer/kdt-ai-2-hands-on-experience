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


# ── wf_external_transfer (계약 5.9) ───────────────────────────────────────────
# UI 계약 식별자.
UI_RECIPIENT_SELECT = "UI-RECIPIENT-SELECT"
UI_EXTERNAL_FROM_ACCOUNT = "UI-EXTERNAL-TRANSFER-FROM-ACCOUNT"
UI_TRANSFER_AMOUNT_INPUT = "UI-TRANSFER-AMOUNT-INPUT"
UI_EXTERNAL_TRANSFER_CONFIRMATION = "UI-EXTERNAL-TRANSFER-CONFIRMATION"
UI_EXTERNAL_TRANSFER_AUTH = "UI-EXTERNAL-TRANSFER-AUTH"
UI_EXTERNAL_TRANSFER_AUTH_RETRY = "UI-EXTERNAL-TRANSFER-AUTH-RETRY"

# 최근 송금 수취인(계약 3.2 initial). Backend 가 마스킹해 제공하는 형태를 모사한다.
RECENT_RECIPIENTS = [
    {
        "to_recipient_id": "rcp_001",
        "name": "홍*동",
        "bank_name": "국민은행",
        "masked_account_number": "123-***-456789",
        "last_transfer_at": "2026-07-01",
    },
    {
        "to_recipient_id": "rcp_002",
        "name": "김*수",
        "bank_name": "카카오뱅크",
        "masked_account_number": "3333-**-987654",
        "last_transfer_at": "2026-06-21",
    },
]


def find_recipient(to_recipient_id: str) -> dict | None:
    """최근 수취인 목록에서 id 로 표시 정보를 찾는다."""
    for recipient in RECENT_RECIPIENTS:
        if recipient["to_recipient_id"] == to_recipient_id:
            return recipient
    return None


def build_recipient_select_view() -> dict:
    """recipient_select initial payload(계약 3.2). 최근 수취인 + 신규 계좌 입력."""
    return {
        "state": "initial",
        "title": "받는 분을 선택해 주세요.",
        "recipient_selection_reason": "no_match",
        "recent_recipients": RECENT_RECIPIENTS,
        "manual_input": {"enabled": True, "fields": ["bank_code", "account_number"]},
        "actions": ["select", "submit_manual", "cancel"],
    }


def build_from_account_view() -> dict:
    """타인송금 출금 계좌 선택 account_card_list payload(계약 3.3)."""
    return {
        "title": "출금할 계좌를 선택해 주세요.",
        "accounts": BALANCE_ACCOUNTS,
        "actions": ["select", "cancel"],
    }


def build_amount_input_view() -> dict:
    """송금 금액 number_input payload(계약 3.4)."""
    return {
        "title": "송금 금액을 입력해 주세요.",
        "currency": "KRW",
        "min": 1,
        "actions": ["submit", "cancel"],
    }


def _account_display(account_id: str) -> dict:
    for account in BALANCE_ACCOUNTS:
        if account["account_id"] == account_id:
            return {
                "bank_name": account["bank_name"],
                "account_alias": account["account_alias"],
                "masked_account_number": account["masked_account_number"],
            }
    return {}


def build_external_transfer_confirm_view(fixed_data: dict) -> dict:
    """타인송금 confirm_modal payload(계약 3.7)."""
    recipient = fixed_data.get("recipient", {})
    return {
        "purpose": "external_transfer",
        "title": "송금 내용을 확인해 주세요.",
        "from_account": _account_display(fixed_data.get("from_account_id", "")),
        "recipient": {
            "name": recipient.get("name"),
            "bank_name": recipient.get("bank_name"),
            "masked_account_number": recipient.get("masked_account_number"),
        },
        "amount": fixed_data.get("amount"),
        "currency": "KRW",
        "allowed_change_targets": ["from_account", "recipient", "amount"],
        "actions": ["approve", "modify", "cancel"],
    }


def build_transfer_result(
    fixed_data: dict, transaction_id: str, completed_at: str
) -> dict:
    """타인송금 transfer_result payload(계약 4.5)."""
    recipient = fixed_data.get("recipient", {})
    return {
        "transaction_id": transaction_id,
        "completed_at": completed_at,
        "from_account": _account_display(fixed_data.get("from_account_id", "")),
        "recipient": {
            "name": recipient.get("name"),
            "bank_name": recipient.get("bank_name"),
            "masked_account_number": recipient.get("masked_account_number"),
        },
        "amount": fixed_data.get("amount"),
        "currency": "KRW",
    }


def build_auth_request_view() -> dict:
    """추가 인증 auth_request payload(계약 3.8). FE 는 비밀번호 재확인으로 처리."""
    return {
        "title": "송금을 계속하려면 비밀번호를 다시 입력해 주세요.",
        "available_methods": ["password"],
        "actions": ["submit", "cancel"],
    }


def build_auth_retry_view() -> dict:
    """재인증 선택 option_select payload(계약 3.6·3.8)."""
    return {
        "title": "인증에 실패했어요. 다시 시도할까요?",
        "options": [
            {"value": "retry", "label": "다시 시도"},
            {"value": "cancelled", "label": "송금 취소"},
        ],
        "actions": ["select"],
    }


# ── 조회 워크플로우 (계약 5.2·5.4·5.5) ────────────────────────────────────────
# UI 계약 식별자.
UI_ACCOUNT_LIST_RESULT = "UI-ACCOUNT-LIST-RESULT"
UI_TRANSACTION_ACCOUNT_SELECTION = "UI-TRANSACTION-ACCOUNT-SELECTION"
UI_SUMMARY_ACCOUNT_SELECTION = "UI-SUMMARY-ACCOUNT-SELECTION"
UI_PERIOD_SELECTION = "UI-PERIOD-SELECTION"
UI_TRANSACTION_LIST = "UI-TRANSACTION-LIST"
UI_SUMMARY_TYPE_SELECTION = "UI-SUMMARY-TYPE-SELECTION"
UI_AMOUNT_SUMMARY = "UI-AMOUNT-SUMMARY"

# 거래내역 목 표본(계약 4.3: transaction_title·부호 있는 amount·occurred_at).
_SAMPLE_TRANSACTIONS = [
    {
        "transaction_id": "txn_001",
        "transaction_title": "편의점",
        "amount": -5200,
        "currency": "KRW",
        "occurred_at": "2026-07-14T20:30:00+09:00",
    },
    {
        "transaction_id": "txn_002",
        "transaction_title": "급여",
        "amount": 3_200_000,
        "currency": "KRW",
        "occurred_at": "2026-07-10T09:00:00+09:00",
    },
    {
        "transaction_id": "txn_003",
        "transaction_title": "카페",
        "amount": -4800,
        "currency": "KRW",
        "occurred_at": "2026-07-08T14:10:00+09:00",
    },
]


def build_account_card_payload(title: str) -> dict:
    """조회 계좌 선택 account_card_list payload(계약 3.3)."""
    return {
        "title": title,
        "accounts": BALANCE_ACCOUNTS,
        "actions": ["select", "cancel"],
    }


def build_account_list() -> dict:
    """계좌 목록 결과 account_list payload(계약 4.1). 잔액·전체 번호는 담지 않는다."""
    accounts = []
    for account in BALANCE_ACCOUNTS:
        accounts.append(
            {
                "account_id": account["account_id"],
                "bank_name": account["bank_name"],
                "account_alias": account["account_alias"],
                "account_type": account["account_type"],
                "masked_account_number": account["masked_account_number"],
                "currency": account["currency"],
                "is_default": account["is_default"],
                "status": "active",
            }
        )
    return {"accounts": accounts}


def build_period_input_view() -> dict:
    """조회 기간 선택 period_input payload(계약 3.5)."""
    return {
        "title": "조회 기간을 선택해 주세요.",
        "presets": ["this_month", "last_month", "recent_1_month"],
        "manual_range": True,
        "actions": ["select", "cancel"],
    }


def build_summary_type_view() -> dict:
    """합계 유형 선택 option_select payload(계약 3.6)."""
    return {
        "title": "합계 유형을 선택해 주세요.",
        "options": [
            {"value": "spending", "label": "지출"},
            {"value": "income", "label": "수입"},
        ],
        "actions": ["select", "cancel"],
    }


def build_transaction_list(
    account_ids: list[str],
    start_date: str | None,
    end_date: str | None,
    transaction_query_id: str,
) -> dict:
    """거래내역 첫 페이지 transaction_list payload(계약 4.3)."""
    return {
        "account_ids": account_ids,
        "period": {"start_date": start_date, "end_date": end_date},
        "transactions": _SAMPLE_TRANSACTIONS,
        "transaction_query_id": transaction_query_id,
        "pagination": {"next_cursor": None},
    }


def build_amount_summary(
    account_ids: list[str],
    start_date: str | None,
    end_date: str | None,
    summary_type: str,
) -> dict:
    """기간 거래 합계 amount_summary payload(계약 4.4)."""
    total = 350_000 if summary_type == "spending" else 3_200_000
    return {
        "account_ids": account_ids,
        "start_date": start_date,
        "end_date": end_date,
        "summary_type": summary_type,
        "total_amount": total,
        "currency": "KRW",
    }


# ── wf_internal_transfer (계약 5.8) ───────────────────────────────────────────
UI_INTERNAL_FROM_ACCOUNT = "UI-INTERNAL-TRANSFER-FROM-ACCOUNT"
UI_INTERNAL_TO_ACCOUNT = "UI-INTERNAL-TRANSFER-TO-ACCOUNT"


def build_internal_transfer_confirm_view(fixed_data: dict) -> dict:
    """본인송금 confirm_modal payload(계약 3.7). 수취인 대신 입금 계좌를 표시."""
    return {
        "purpose": "internal_transfer",
        "title": "본인 계좌 이체 내용을 확인해 주세요.",
        "from_account": _account_display(fixed_data.get("from_account_id", "")),
        "to_account": _account_display(fixed_data.get("to_account_id", "")),
        "amount": fixed_data.get("amount"),
        "currency": "KRW",
        "allowed_change_targets": ["from_account", "to_account", "amount"],
        "actions": ["approve", "modify", "cancel"],
    }


def build_internal_transfer_result(
    fixed_data: dict, transaction_id: str, completed_at: str
) -> dict:
    """본인송금 transfer_result payload(계약 4.5). recipient 대신 입금 계좌 표시."""
    to_account = _account_display(fixed_data.get("to_account_id", ""))
    return {
        "transaction_id": transaction_id,
        "completed_at": completed_at,
        "from_account": _account_display(fixed_data.get("from_account_id", "")),
        "recipient": {
            "name": to_account.get("account_alias"),
            "bank_name": to_account.get("bank_name"),
            "masked_account_number": to_account.get("masked_account_number"),
        },
        "amount": fixed_data.get("amount"),
        "currency": "KRW",
    }


# ── wf_set_default_account (계약 5.6) ─────────────────────────────────────────
UI_DEFAULT_ACCOUNT_SELECTION = "UI-DEFAULT-ACCOUNT-SELECTION"


def build_default_account_confirm_view(account_id: str) -> dict:
    """기본 출금 계좌 변경 confirm_modal payload(계약 3.7)."""
    display = _account_display(account_id)
    return {
        "purpose": "default_account",
        "title": "기본 출금 계좌를 변경할까요?",
        "account": {
            "account_id": account_id,
            "bank_name": display.get("bank_name"),
            "masked_account_number": display.get("masked_account_number"),
        },
        "allowed_change_targets": [],
        "actions": ["approve", "cancel"],
    }


def build_default_account_result(account_id: str, completed_at: str) -> dict:
    """기본 출금 계좌 변경 setting_result payload(계약 4.6)."""
    display = _account_display(account_id)
    return {
        "purpose": "default_account",
        "outcome": "completed",
        "account": {
            "account_id": account_id,
            "masked_account_number": display.get("masked_account_number"),
        },
        "completed_at": completed_at,
    }
