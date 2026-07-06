"""Tool Registry.

YAML의 tool_id 문자열과 실제 Python 함수를 연결한다.
새 Tool을 추가하려면 bank_tools에 함수를 만들고 여기에 한 줄 등록하면 된다.

참고: 시트가 response 스텝에 적는 'final_response'는 실존 tool이 아니라
의도적으로 미등록이다 — 엔진(subgraph_builder)의 response 노드 폴백이
step_message/final_response 표시를 담당한다.
"""

from agent.tools.bank_tools import (
    apply_account_selection,
    check_amount_input,
    check_balance,
    check_recipient_input,
    create_approval,
    extract_balance_slots,
    extract_transfer_slots,
    generate_balance_response,
    generate_transfer_response,
    get_balance,
    request_user_authentication,
    resolve_recipient_input,
    run_pre_execution_guardrail,
    run_transfer_guardrail,
    transfer_money,
    transfer_warning,
    verify_account,
    verify_amount,
    verify_from_account,
    verify_recipient_account,
    write_audit_log,
)

TOOL_REGISTRY = {
    # 공통
    "write_audit_log": write_audit_log,
    # 잔액조회
    "extract_balance_slots": extract_balance_slots,
    "verify_account": verify_account,
    "apply_account_selection": apply_account_selection,
    "get_balance": get_balance,
    # 시트 모순 흡수: Step 시트는 get_balance, Tool_v2는 fetch_balance를 쓴다.
    # 둘 다 같은 함수로 등록한다 (agent/docs/agent-sheet-v2-review.md 참조).
    "fetch_balance": get_balance,
    "generate_balance_response": generate_balance_response,
    # 타인 송금 — 슬롯 추출 / 입력 확인
    "extract_transfer_slots": extract_transfer_slots,
    "check_recipient_input": check_recipient_input,
    "resolve_recipient_input": resolve_recipient_input,
    "verify_recipient_account": verify_recipient_account,
    "check_amount_input": check_amount_input,
    # 타인 송금 — 검증
    "verify_amount": verify_amount,
    "verify_from_account": verify_from_account,
    "check_balance": check_balance,
    # 타인 송금 — 정책 검사
    "run_transfer_guardrail": run_transfer_guardrail,
    "run_pre_execution_guardrail": run_pre_execution_guardrail,
    # 타인 송금 — 대화형 (interrupt)
    "transfer_warning": transfer_warning,
    "create_approval": create_approval,
    "request_user_authentication": request_user_authentication,
    # 타인 송금 — 실행 / 응답
    "transfer_money": transfer_money,
    "generate_transfer_response": generate_transfer_response,
}


def get_tool(tool_id: str):
    """tool_id에 해당하는 함수를 반환한다. 없으면 KeyError를 던진다."""
    if tool_id not in TOOL_REGISTRY:
        raise KeyError(f"등록되지 않은 tool_id: {tool_id}")
    return TOOL_REGISTRY[tool_id]
