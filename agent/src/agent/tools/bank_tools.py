"""은행 Tool 함수 모음.

설계 원칙: Tool은 '실제 기능 단위'로만 만든다. 여러 Workflow가 같은 Tool을 재사용한다.
모든 Tool은 `state: dict`를 받아 결과 값을 반환한다.

state 규약 (시트 v2 / Tool_v2 계약):
  - 업무 데이터는 state["data"]에 네임스페이스 키로 들어 있다
    (예: "balance.account_hint"). 읽을 때는 _data(state) 헬퍼를 쓴다.
  - 반환 dict의 업무 키도 네임스페이스 키로 쓴다. 엔진(subgraph_builder)이
    시스템 키(route_key, final_response 등)는 top-level로, 나머지는
    data 버킷으로 분리해 저장한다.
  - 변경분(delta)만 반환한다. state를 in-place로 수정하지 않는다.
  - dict의 "route_key"로 다음 라우트를 지정한다. None 반환 → error 라우팅.
"""

from __future__ import annotations

import re
import time

from pydantic import BaseModel, Field

from agent.data.mock_bank import MOCK_ACCOUNTS, MOCK_RECIPIENTS
from agent.llm import get_llm


def _data(state: dict) -> dict:
    """AgentState의 업무 데이터 버킷(data)을 반환한다."""
    return state.get("data") or {}


# ── 공통 조회 ──────────────────────────────────────────────────────────────────


def get_accounts(state: dict) -> list | None:
    """user_id 기준 계좌 목록을 반환한다."""
    user_id = state.get("user_id")
    accounts = MOCK_ACCOUNTS.get(user_id, [])
    return accounts if accounts else None


def resolve_account(state: dict) -> dict | None:
    """조회/출금 계좌를 결정한다.

    계좌가 1개면 그것을, 여러 개면 기본 계좌(is_default=True)를 선택한다.
    기본 계좌도 없으면 None 반환 → on_fail로 사용자에게 선택 요청.
    """
    accounts = state.get("accounts") or []
    if not accounts:
        return None
    if len(accounts) == 1:
        return accounts[0]
    for account in accounts:
        if account.get("is_default"):
            return account
    return None


def get_balance(state: dict) -> dict:
    """확정된 계좌들의 잔액 정보를 balance.balance_results(리스트)로 반환한다.

    잔액조회 전용 tool이다. 송금의 잔액확인은 별도 tool(check_balance)이 담당한다.
    Tool_v2에서는 fetch_balance라는 id로 정의되어 있다 (registry에 alias 등록).
    """
    accounts = _data(state).get("balance.selected_accounts") or []
    if not accounts:
        return {"route_key": "failed"}

    results = [
        {
            "account_id": a["account_id"],
            "account_name": a["account_name"],
            "balance": a["balance"],
            "currency": a.get("currency", "KRW"),
        }
        for a in accounts
    ]
    return {"balance.balance_results": results, "route_key": "success"}


# ── 잔액조회 ───────────────────────────────────────────────────────────────────

_BALANCE_KEYWORDS = ["생활비", "입출금", "저축", "적금", "주거래"]


class _BalanceSlots(BaseModel):
    """잔액 조회 발화에서 뽑는 슬롯."""

    account_hint: str | None = Field(
        None,
        description=(
            "사용자가 언급한 계좌의 핵심 단어. 계좌명에 그대로 포함될 수 있는 "
            "단어여야 하며 조사·공백은 빼라(예: '생활비', '입출금', '저축'). "
            "특정 계좌를 지칭하지 않으면 null."
        ),
    )


def _extract_balance_hint_by_keyword(user_input: str) -> str | None:
    """규칙 기반 폴백: 키워드가 발화에 있으면 그 키워드를 힌트로 쓴다."""
    for keyword in _BALANCE_KEYWORDS:
        if keyword in user_input:
            return keyword
    return None


def extract_balance_slots(state: dict) -> dict:
    """발화에서 계좌 힌트를 추출한다. 항상 route_key='extracted'를 반환한다.

    LLM structured output으로 힌트를 뽑고, 실패 시 키워드 매칭으로 폴백한다.
    """
    user_input = state.get("user_input", "")

    try:
        llm = get_llm().with_structured_output(_BalanceSlots)
        result = llm.invoke(
            f"다음 사용자 발화에서 조회하려는 계좌 힌트를 추출해라.\n발화: {user_input}"
        )
        account_hint = result.account_hint or None
    except Exception:
        account_hint = None

    # LLM이 못 뽑았으면(None) 키워드 매칭으로 보강한다.
    # ('입출금' 같은 계좌유형을 LLM이 일반 명사로 오판해 놓치는 경우 방지)
    if not account_hint:
        account_hint = _extract_balance_hint_by_keyword(user_input)

    return {"balance.account_hint": account_hint, "route_key": "extracted"}


def verify_account(state: dict) -> dict:
    """잔액 조회 대상 계좌를 확정한다(복수 지원).

    힌트로 계좌가 하나로 특정되면 confirmed.
    여러 개면 select_needed → 사용자에게 되물어 선택받는다(복수 선택 가능).
    결과는 항상 balance.selected_accounts(리스트)에 담는다.
    예기치 못한 오류는 error 라우트로 보낸다 (시트 v2 신규 라우트).
    """
    try:
        user_id = state.get("user_id")
        accounts = MOCK_ACCOUNTS.get(user_id, [])
        if not accounts:
            return {
                "balance.selected_accounts": [],
                "balance.account_candidates": [],
                "route_key": "not_found",
            }

        # 공백 무시 매칭 — LLM이 '생활비 통장'처럼 공백을 넣어도 '생활비통장'에 매칭
        hint = (_data(state).get("balance.account_hint") or "").replace(" ", "")
        if hint:
            candidates = [
                a
                for a in accounts
                if hint in a.get("account_name", "").replace(" ", "")
            ]
        else:
            candidates = accounts

        if not candidates:
            return {
                "balance.selected_accounts": [],
                "balance.account_candidates": [],
                "route_key": "not_found",
            }
        if len(candidates) == 1:
            # 하나로 특정됨 → 바로 확정
            return {
                "balance.selected_accounts": candidates,
                "balance.account_candidates": candidates,
                "route_key": "confirmed",
            }
        # 여러 개 → 되물어 선택받는다. 선택지 메시지(목록 포함)를 만들어 담는다.
        options = "\n".join(
            f"  {i}. {a['account_name']}" for i, a in enumerate(candidates, 1)
        )
        prompt = f"조회할 계좌를 선택해 주세요 (여러 개 가능):\n{options}"
        return {
            "balance.selected_accounts": [],
            "balance.account_candidates": candidates,
            "prompt_message": prompt,
            "route_key": "select_needed",
        }
    except Exception:
        return {"route_key": "error"}


def generate_balance_response(state: dict) -> dict:
    """balance.balance_results를 사람이 읽을 응답 문장으로 만든다.

    LLM이 자연스러운 문장을 생성하되, 금액·계좌명은 코드가 프롬프트에 주입해
    LLM이 수치를 지어내지 못하게 한다. LLM 호출 실패 시 규칙 기반으로 폴백한다.
    """
    results = _data(state).get("balance.balance_results") or []
    if not results:
        return {"route_key": "failed"}

    # 코드가 만든 확정 응답 — LLM 실패 시 폴백으로도 사용
    fallback = (
        ", ".join(f"{r['account_name']} {r['balance']:,}원" for r in results)
        + "입니다."
    )

    try:
        info = "\n".join(f"- {r['account_name']}: {r['balance']:,}원" for r in results)
        prompt = (
            "너는 은행 앱의 친절한 상담원이다. 아래 계좌들의 잔액을 "
            "자연스러운 한국어 존댓말 한 문장으로 안내해라. "
            "숫자와 계좌명은 절대 바꾸지 말고, 이모지 없이 간결하게.\n"
            f"{info}"
        )
        text = (get_llm().invoke(prompt).content or "").strip()
        final = text or fallback
    except Exception:
        final = fallback

    return {"final_response": final, "route_key": "success"}


class _AccountSelection(BaseModel):
    """사용자 답변에서 파싱한 계좌 선택 (LLM structured output용)."""

    selected_numbers: list[int] = Field(
        default_factory=list,
        description=(
            "사용자가 선택한 계좌의 1-기반 번호 목록. "
            "예: '1번이랑 3번' → [1, 3], '둘 다'/'전부' → 모든 번호."
        ),
    )


def apply_account_selection(state: dict) -> dict:
    """계좌 선택 답변을 파싱해 balance.selected_accounts를 확정한다(복수 가능).

    LLM으로 '1번이랑 2번', '둘 다' 같은 자연어 답변에서 선택 계좌를 뽑는다.
    유효한 선택이 없으면 invalid → 다시 묻는다.
    """
    reply = _data(state).get("balance.account_selection_input", "")
    candidates = _data(state).get("balance.account_candidates") or []
    if not candidates:
        return {"route_key": "invalid"}

    try:
        menu = "\n".join(
            f"{i + 1}. {a['account_name']}" for i, a in enumerate(candidates)
        )
        llm = get_llm().with_structured_output(_AccountSelection)
        result = llm.invoke(
            "사용자가 아래 계좌 목록 중에서 조회할 계좌를 선택했다. "
            "선택한 계좌의 번호를 모두 골라라.\n"
            f"[계좌 목록]\n{menu}\n\n[사용자 답변]\n{reply}"
        )
        nums = [n for n in (result.selected_numbers or []) if 1 <= n <= len(candidates)]
    except Exception:
        nums = []

    if not nums:
        return {"route_key": "invalid"}

    selected = [candidates[n - 1] for n in nums]
    return {"balance.selected_accounts": selected, "route_key": "selected"}


# ═══════════════════════════════════════════════════════════════════════════
# 레거시 송금 tool (Tool_v2 이전 스펙 — 재작성 예정)
#
# 아래 함수들은 구버전 시트 기준으로 작성되어 flat top-level 키
# (recipient_name, selected_account, amount 등)를 읽는다. state 개편 이후
# 이 키들은 data 버킷에 네임스페이스(transfer.*)로 들어오므로 이 함수들은
# 값을 찾지 못해 None을 반환하고, 엔진이 error 라우팅한다 (안전하게 실패).
# wf_external_transfer 구현 시 Tool_v2의 input_state_keys/write_state_keys
# 계약대로 재작성한다. 목록: docs/agent-sheet-v2-review.md 참조.
#
# 알려진 잠재 버그: create_approval은 state를 in-place로 수정한다
# (state["approval_prompt"] = ...) — 재작성 시 delta 반환으로 교체할 것.
#
# 예외: 맨 아래 '감사 로그' 섹션(write_audit_log)은 시스템 키만 다루므로
# 레거시가 아니며 balance/transfer 양쪽에서 그대로 사용된다.
# ═══════════════════════════════════════════════════════════════════════════

# ── 타인 송금 슬롯 추출 ────────────────────────────────────────────────────────


def extract_transfer_slots(state: dict) -> dict | None:
    """사용자 발화에서 수취인명·금액·계좌 힌트를 추출한다.

    결과를 multi-key output_data_key(recipient_name, amount, account)로 반환.
    추출된 것이 없으면 None → on_fail_next_step_id(ask_transfer_info)로 라우팅.
    """
    user_input = state.get("user_input", "")
    slots: dict = {}

    m = re.search(r"(\S+)(?:에게|한테|에게로)", user_input)
    if m:
        slots["recipient_name"] = m.group(1)

    m = re.search(r"(\d+)\s*만\s*원", user_input)
    if m:
        slots["amount"] = int(m.group(1)) * 10000
    else:
        m = re.search(r"(\d[\d,]*)\s*원", user_input)
        if m:
            slots["amount"] = int(m.group(1).replace(",", ""))

    if not slots:
        return None

    return {
        "recipient_name": slots.get("recipient_name"),
        "amount": slots.get("amount"),
        "account": slots.get("account_hint"),
    }


# ── 수취인 확인 ────────────────────────────────────────────────────────────────


def verify_recipient(state: dict) -> dict | None:
    """수취인 이름으로 등록 수취인을 검색해 단일 매칭 시 확정한다.

    이미 selected_recipient가 있으면 그대로 통과.
    단일 매칭 → 성공.
    복수/미매칭 → _success: False (ask_recipient_resolution으로 라우팅).
    """
    if state.get("selected_recipient"):
        rec = state["selected_recipient"]
        return {
            "recipient_candidates": [rec],
            "selected_recipient": rec,
            "recipient_verification_result": "matched",
        }

    user_id = state.get("user_id")
    name = (state.get("recipient_name") or "").strip()
    if not name:
        return None

    candidates = [r for r in MOCK_RECIPIENTS.get(user_id, []) if name in r["name"]]

    if len(candidates) == 1:
        return {
            "recipient_candidates": candidates,
            "selected_recipient": candidates[0],
            "recipient_verification_result": "matched",
        }
    elif len(candidates) > 1:
        return {
            "_success": False,
            "recipient_candidates": candidates,
            "selected_recipient": None,
            "recipient_verification_result": "multiple",
        }
    else:
        return {
            "_success": False,
            "recipient_candidates": [],
            "selected_recipient": None,
            "recipient_verification_result": "no_match",
        }


# ── 출금 계좌 확인 ─────────────────────────────────────────────────────────────


def verify_from_account(state: dict) -> dict | None:
    """출금 계좌를 확정한다.

    이미 selected_account가 있으면 유효성 검증 후 통과.
    단일 계좌 또는 기본 계좌 → 성공.
    후보 복수에 기본 계좌 없음 → _success: False (ask_account_selection으로 라우팅).
    """
    user_id = state.get("user_id")
    accounts = MOCK_ACCOUNTS.get(user_id, [])
    if not accounts:
        return None

    already = state.get("selected_account")
    if already and isinstance(already, dict):
        if any(a["account_id"] == already["account_id"] for a in accounts):
            return {
                "account_candidates": accounts,
                "selected_account": already,
                "account_verification_result": "matched",
            }

    hint = (state.get("account_hint") or state.get("account") or "").strip()
    candidates = (
        [a for a in accounts if hint in a.get("account_name", "")] if hint else accounts
    )

    if len(candidates) == 1:
        return {
            "account_candidates": candidates,
            "selected_account": candidates[0],
            "account_verification_result": "matched",
        }

    for a in candidates:
        if a.get("is_default"):
            return {
                "account_candidates": candidates,
                "selected_account": a,
                "account_verification_result": "matched",
            }

    return {
        "_success": False,
        "account_candidates": candidates,
        "selected_account": None,
        "account_verification_result": "multiple",
    }


# ── 금액 검증 ──────────────────────────────────────────────────────────────────


def verify_amount(state: dict) -> dict | None:
    """송금 금액의 유효성을 검증한다."""
    amount = state.get("amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        return {
            "_success": False,
            "amount": None,
            "amount_verification_result": "invalid",
        }
    if amount > 50_000_000:
        return {
            "_success": False,
            "amount": amount,
            "amount_verification_result": "limit_exceeded",
        }
    return {"amount": int(amount), "amount_verification_result": "valid"}


# ── 위험도 평가 ────────────────────────────────────────────────────────────────


def assess_transfer_risk(state: dict) -> dict | None:
    """송금 위험도를 평가한다.

    1천만 원 이상 → 고위험(blocked).
    그 외 → 통과 (백만 원 이상은 R4, 미만은 R2).
    """
    amount = state.get("amount", 0)

    if amount >= 10_000_000:
        return {
            "_success": False,
            "risk_result": {
                "risk_level": "R5",
                "decision": "blocked",
                "reason": f"{amount:,}원 — 1천만 원 이상 고액 송금",
            },
        }

    return {
        "risk_result": {
            "risk_level": "R4" if amount >= 1_000_000 else "R2",
            "decision": "pass",
        }
    }


# ── 승인 관리 ──────────────────────────────────────────────────────────────────


def create_approval(state: dict) -> dict | None:
    """송금 승인 요청 정보를 생성하고 approval_prompt를 설정한다."""
    recipient = state.get("selected_recipient") or {}
    account = state.get("selected_account") or {}
    amount = state.get("amount", 0)
    memo = state.get("memo") or ""

    approval_id = state.get("approval_id") or f"apv_{int(time.time())}"

    memo_line = f"\n  메모      : {memo}" if memo else ""
    state["approval_prompt"] = (
        f"[송금 확인]\n"
        f"  받는 분   : {recipient.get('name', '?')} ({recipient.get('bank', '?')})\n"
        f"  보내는 계좌: {account.get('account_name', '?')}\n"
        f"  금액      : {amount:,}원{memo_line}\n"
        f"송금하시겠습니까? (확인/취소)"
    )
    state["final_response"] = state["approval_prompt"]

    return {
        "approval_id": approval_id,
        "approval_summary": {
            "recipient_name": recipient.get("name"),
            "recipient_bank": recipient.get("bank"),
            "from_account": account.get("account_name"),
            "amount": amount,
            "memo": memo,
        },
    }


def check_approval_result(state: dict) -> dict | None:
    """approval_status를 확인해 승인 결과를 반환한다.

    approved → {"approval_result": "approved"}.
    그 외 → None (on_fail_next_step_id: show_transfer_cancelled 으로 라우팅).
    """
    if state.get("approval_status") == "approved":
        return {"approval_result": "approved"}
    return None


# ── 송금 실행 ──────────────────────────────────────────────────────────────────


def transfer_money(state: dict) -> dict | None:
    """타인 송금을 실행한다. 잔액을 실제로 차감하고 거래 기록을 반환한다."""
    from_account = state.get("selected_account")
    recipient = state.get("selected_recipient")
    amount = state.get("amount")
    memo = state.get("memo", "")

    if not from_account or not recipient or not amount:
        return None
    if from_account.get("balance", 0) < amount:
        return None

    from_account["balance"] -= amount

    return {
        "transaction_id": f"txn_{int(time.time())}",
        "from_account_id": from_account["account_id"],
        "to_recipient_id": recipient["recipient_id"],
        "to_recipient_name": recipient["name"],
        "amount": amount,
        "memo": memo,
        "status": "completed",
    }


def generate_transfer_response(state: dict) -> str | None:
    """송금 결과를 사람이 읽을 응답 문자열로 만든다."""
    result = state.get("transfer_result")
    if not result or result.get("status") != "completed":
        return None
    memo = f" (메모: {result['memo']})" if result.get("memo") else ""
    return (
        f"{result['to_recipient_name']}님에게 {result['amount']:,}원을 송금했습니다."
        f"{memo} 거래번호: {result['transaction_id']}"
    )


# ── 구 호환 (wf_balance_inquiry 등) ────────────────────────────────────────────


def search_recipient(state: dict) -> dict | None:
    """수취인 이름으로 등록 수취인을 검색한다 (구 버전 호환)."""
    user_id = state.get("user_id")
    slots = state.get("transfer_slots") or {}
    name = slots.get("recipient_name") or state.get("recipient_name", "")
    if not name:
        return None
    candidates = [r for r in MOCK_RECIPIENTS.get(user_id, []) if name in r["name"]]
    return candidates[0] if candidates else None


# ── 감사 로그 ──────────────────────────────────────────────────────────────────

_FAIL_KEYS = {"failed", "not_found", "error", "log_failed", "insufficient"}


def _format_execution_trace(log: dict) -> str:
    """execution_trace를 프론트엔드에 전달 가능한 plain string으로 변환한다."""
    lines = [
        f"📋 {log['log_id']} | {log.get('workflow_id', '-')}",
        f"💬 {log.get('final_response', '(응답 없음)')}",
        "",
        "실행 경로:",
    ]
    for i, t in enumerate(log.get("execution_trace", [])):
        prefix = "  " if i == 0 else "  → "
        rkey = t.get("route_key") or ""
        mark = " ← 차단" if rkey in _FAIL_KEYS else ""
        lines.append(f"{prefix}{t['step']} [{rkey}]{mark}")
    lines.append("  → END")
    return "\n".join(lines)


def write_audit_log(state: dict) -> dict:
    """실행 내역을 감사 로그에 기록한다."""
    logs = list(state.get("logs") or [])
    log_id = f"log_{len(logs) + 1:04d}"
    entry = {
        "log_id": log_id,
        "user_id": state.get("user_id"),
        "workflow_id": state.get("workflow_id"),
        "final_response": state.get("final_response"),
        "execution_trace": state.get("execution_trace", []),
        "execution_trace_text": _format_execution_trace(
            {
                "log_id": log_id,
                "workflow_id": state.get("workflow_id"),
                "final_response": state.get("final_response"),
                "execution_trace": state.get("execution_trace", []),
            }
        ),
    }
    return {"log_id": log_id, "logs": logs + [entry], "route_key": "logged"}
