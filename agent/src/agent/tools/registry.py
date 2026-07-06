"""Tool Registry.

YAML의 tool_id 문자열과 실제 Python 함수를 연결한다.
새 Tool을 추가하려면 bank_tools에 함수를 만들고 여기에 한 줄 등록하면 된다.
"""

from agent.tools.bank_tools import (
    apply_account_selection,
    assess_transfer_risk,
    check_approval_result,
    create_approval,
    extract_balance_slots,
    extract_transfer_slots,
    generate_balance_response,
    generate_transfer_response,
    get_accounts,
    get_balance,
    resolve_account,
    search_recipient,
    transfer_money,
    verify_account,
    verify_amount,
    verify_from_account,
    verify_recipient,
    write_audit_log,
)

TOOL_REGISTRY = {
    # 공통
    "get_accounts": get_accounts,
    "resolve_account": resolve_account,
    "write_audit_log": write_audit_log,
    # 잔액조회
    "extract_balance_slots": extract_balance_slots,
    "verify_account": verify_account,
    "apply_account_selection": apply_account_selection,
    "get_balance": get_balance,
    # 시트 모순 흡수: Step 시트는 get_balance, Tool_v2는 fetch_balance를 쓴다.
    # 둘 다 같은 함수로 등록한다 (docs/agent-sheet-v2-review.md 참조).
    "fetch_balance": get_balance,
    "generate_balance_response": generate_balance_response,
    # 타인 송금 — 슬롯 추출
    "extract_transfer_slots": extract_transfer_slots,
    # 타인 송금 — 검증
    "verify_recipient": verify_recipient,
    "verify_from_account": verify_from_account,
    "verify_amount": verify_amount,
    # 타인 송금 — 위험도 / 승인
    "assess_transfer_risk": assess_transfer_risk,
    "create_approval": create_approval,
    "check_approval_result": check_approval_result,
    # 타인 송금 — 실행 / 응답
    "transfer_money": transfer_money,
    "generate_transfer_response": generate_transfer_response,
    # 구 버전 호환
    "search_recipient": search_recipient,
}


def get_tool(tool_id: str):
    """tool_id에 해당하는 함수를 반환한다. 없으면 KeyError를 던진다."""
    if tool_id not in TOOL_REGISTRY:
        raise KeyError(f"등록되지 않은 tool_id: {tool_id}")
    return TOOL_REGISTRY[tool_id]
