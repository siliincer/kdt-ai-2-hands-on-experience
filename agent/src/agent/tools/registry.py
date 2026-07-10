"""Tool Registry.

YAML의 tool_id 문자열과 실제 Python 함수를 연결한다.
새 Tool을 추가하려면 bank_tools에 함수를 만들고 여기에 한 줄 등록하면 된다.

참고: 시트가 response 스텝에 적는 'final_response'는 실존 tool이 아니라
의도적으로 미등록이다 — 엔진(subgraph_builder)의 response 노드 폴백이
step_message/final_response 표시를 담당한다.
"""

from agent.tools.bank_tools import (
    apply_account_selection,
    authenticate_user,
    check_amount_input,
    check_balance,
    check_recipient_input,
    confirm_transfer_warning,
    execute_transfer,
    extract_balance_slots,
    extract_transfer_slots,
    fetch_account_list,
    fetch_balance,
    generate_account_list_response,
    generate_balance_response,
    generate_transfer_response,
    request_transfer_approval,
    resolve_recipient_input,
    run_pre_execution_guardrail,
    run_transfer_guardrail,
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
    "fetch_balance": fetch_balance,
    "generate_balance_response": generate_balance_response,
    # 계좌 목록 조회
    "fetch_account_list": fetch_account_list,
    "generate_account_list_response": generate_account_list_response,
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
    "confirm_transfer_warning": confirm_transfer_warning,
    "request_transfer_approval": request_transfer_approval,
    "authenticate_user": authenticate_user,
    # 타인 송금 — 실행 / 응답
    "execute_transfer": execute_transfer,
    "generate_transfer_response": generate_transfer_response,
}


def get_tool(tool_id: str):
    """tool_id에 해당하는 함수를 반환한다. 없으면 KeyError를 던진다."""
    if tool_id not in TOOL_REGISTRY:
        raise KeyError(f"등록되지 않은 tool_id: {tool_id}")
    return TOOL_REGISTRY[tool_id]
