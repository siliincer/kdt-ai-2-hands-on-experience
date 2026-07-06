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

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agent.bank_client import BankClientError, get_bank_client
from agent.llm import get_llm


def _data(state: dict) -> dict:
    """AgentState의 업무 데이터 버킷(data)을 반환한다."""
    return state.get("data") or {}


def _accounts(user_id: str) -> list[dict]:
    """BankClient 경유 계좌 목록 조회 (원장 직접 접근 금지)."""
    return get_bank_client().get_accounts(user_id)


def _recipients(user_id: str) -> list[dict]:
    """BankClient 경유 수취인 목록 조회."""
    return get_bank_client().get_recipients(user_id)


# ── 공통 조회 ──────────────────────────────────────────────────────────────────


def get_balance(state: dict) -> dict:
    """확정된 계좌들의 잔액 정보를 balance.balance_results(리스트)로 반환한다.

    잔액조회 전용 tool이다. 송금의 잔액확인은 별도 tool(check_balance)이 담당한다.
    Tool_v2에서는 fetch_balance라는 id로 정의되어 있다 (registry에 alias 등록).
    """
    accounts = _data(state).get("balance.selected_accounts") or []
    if not accounts:
        return {"route_key": "failed"}

    user_id = state.get("user_id")
    results = []
    for a in accounts:
        # 원장 실시간 재조회 — 실패 시 선택 시점 스냅샷으로 폴백
        try:
            live = _live_account(user_id, a.get("account_id")) or a
        except BankClientError:
            live = a
        results.append(
            {
                "account_id": live["account_id"],
                "account_name": live["account_name"],
                "balance": live["balance"],
                "currency": live.get("currency", "KRW"),
            }
        )
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
        accounts = _accounts(user_id)
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
            "prompt_ui": _account_card_ui(candidates, multi=True),
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
# 타인 송금 (wf_external_transfer) — Tool_v2 계약 구현
#
# 규칙:
#   - 업무 키는 transfer.* 네임스페이스로 읽고(_data) 쓴다(반환 dict)
#   - 모든 tool은 route_key를 명시적으로 반환한다
#   - 승인/인증/경고확인 tool은 직접 interrupt()를 호출한다 (대화형).
#     재개 시 노드가 처음부터 재실행되므로 interrupt 이전 코드는
#     프롬프트 조립 같은 멱등 작업만 둔다. 한 노드 실행에서 interrupt를
#     두 번 호출하지 않는다 (재개 매칭이 위치 기반이라 깨지기 쉬움).
#   - 승인 게이트에서 해석 불가능한 답변은 보수적으로 '취소' 처리한다
# ═══════════════════════════════════════════════════════════════════════════

# ── 파싱/해석 헬퍼 (순수 함수) ─────────────────────────────────────────────────

_AMOUNT_MAN = re.compile(r"(\d[\d,]*)\s*만\s*원?")
_AMOUNT_WON = re.compile(r"(\d[\d,]*)\s*원")
_RECIPIENT_PATTERN = re.compile(r"(\S+?)(?:에게|한테|께)")
_FROM_ACCOUNT_PATTERN = re.compile(r"(\S+?)\s*(?:통장|계좌)\s*에서")
_ACCOUNT_KEYWORDS = ["생활비", "입출금", "저축", "적금", "주거래"]

# 취소로 인식하는 답변 (subgraph_builder._is_cancel_reply와 동일 기준 —
# import하면 순환 참조가 생겨 여기 별도로 둔다)
_CANCEL_EXACT = {"그만", "그만할래", "안할래", "안 할래", "됐어", "관둘래"}


def _is_cancel(reply: str) -> bool:
    text = str(reply).strip()
    return "취소" in text or text in _CANCEL_EXACT


def _parse_amount(value) -> int | None:
    """금액 입력을 정수(원)로 정규화한다. 해석 불가면 None.

    지원: 50000, 50000.0, "5만원", "5만", "50,000원", "50000"
    미지원(한계): "1만 5천원" 같은 혼합 단위 표기.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    m = _AMOUNT_MAN.search(text)
    if m:
        return int(m.group(1).replace(",", "")) * 10000
    m = _AMOUNT_WON.search(text)
    if m:
        return int(m.group(1).replace(",", ""))
    bare = text.replace(",", "")
    if bare.isdigit():
        return int(bare)
    return None


def _resolve_recipient(user_id: str, raw) -> tuple[dict | None, list[dict]]:
    """수취인 입력(이름/계좌번호/dict)을 등록 수취인 단건으로 해석한다.

    반환: (단건 매칭된 수취인 dict 또는 None, 매칭 후보 리스트)
    """
    recipients = _recipients(user_id)
    if isinstance(raw, dict):
        if raw.get("account_number") and raw.get("bank"):
            return raw, [raw]
        raw = raw.get("name") or ""
    text = str(raw or "").strip()
    if not text:
        return None, []
    normalized = text.replace("-", "").replace(" ", "")
    if normalized.isdigit():
        matches = [
            r for r in recipients if r["account_number"].replace("-", "") == normalized
        ]
    else:
        matches = [r for r in recipients if text in r["name"] or r["name"] in text]
    if len(matches) == 1:
        return matches[0], matches
    return None, matches


def _live_account(user_id: str, account_id: str | None) -> dict | None:
    """원장에서 계좌를 실시간 재조회한다 (state 복사본의 잔액은
    오래됐을 수 있으므로 잔액 확인은 반드시 이 결과로 한다)."""
    if not account_id:
        return None
    accounts = get_bank_client().get_accounts(user_id, account_id=account_id)
    return accounts[0] if accounts else None


def _resolve_from_account(user_id: str, raw) -> tuple[dict | None, list[dict]]:
    """출금 계좌 입력(dict/힌트 문자열/"1번"/None)을 계좌 단건으로 해석한다.

    입력이 없으면 기본 계좌(is_default)를 쓴다.
    반환: (해석된 계좌 dict 또는 None, 선택지 후보 리스트)
    """
    accounts = _accounts(user_id)
    if not accounts:
        return None, []
    if isinstance(raw, dict):
        live = _live_account(user_id, raw.get("account_id"))
        return live, accounts
    text = str(raw or "").strip()
    if text:
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            index = int(digits)
            if 1 <= index <= len(accounts):
                return accounts[index - 1], accounts
        compact = text.replace(" ", "")
        matches = [
            a
            for a in accounts
            if compact in a["account_name"].replace(" ", "")
            or a["account_name"].replace(" ", "") in compact
        ]
        if len(matches) == 1:
            return matches[0], accounts
        return None, accounts
    defaults = [a for a in accounts if a.get("is_default")]
    if len(defaults) == 1:
        return defaults[0], accounts
    if len(accounts) == 1:
        return accounts[0], accounts
    return None, accounts


def _parse_approval_reply(reply: str) -> str:
    """승인 카드 답변 → route_key. 해석 불가는 보수적으로 cancelled."""
    text = str(reply).strip()
    if _is_cancel(text):
        return "cancelled"
    if "수취인" in text:
        return "edit_recipient"
    if "금액" in text:
        return "edit_amount"
    if "계좌" in text:
        return "edit_from_account"
    approve_keywords = ("승인", "확인", "네", "응", "보내", "진행", "예")
    if any(keyword in text for keyword in approve_keywords):
        return "approved"
    # UI 승인 버튼 라벨("송금하기")이 그대로 회신되는 경우 — 정확 일치만
    # 허용한다 ("송금 안 할래" 같은 부정 표현의 오판 방지).
    if text.replace(" ", "") in {"송금하기", "송금"}:
        return "approved"
    return "cancelled"


def _parse_auth_reply(reply: str) -> str:
    """본인 인증 답변 → route_key. 취소/실패를 먼저 검사한다."""
    text = str(reply).strip()
    if _is_cancel(text) or "실패" in text:
        return "not_authenticated"
    auth_keywords = ("인증", "완료", "성공", "했어")
    if any(keyword in text for keyword in auth_keywords):
        return "authenticated"
    return "not_authenticated"


def _parse_warning_reply(reply: str) -> str:
    """주의 안내 답변 → route_key. 명시적 취소만 중단, 그 외는 진행."""
    return "cancelled" if _is_cancel(reply) else "confirmed"


def _account_options(accounts: list[dict]) -> str:
    return "\n".join(
        f"  {i}. {a['account_name']} (잔액 {a['balance']:,}원)"
        for i, a in enumerate(accounts, 1)
    )


def _recipient_catalog(user_id: str) -> str:
    return "\n".join(
        f"  {i}. {r['name']} ({r['bank']} {r['account_number']})"
        for i, r in enumerate(_recipients(user_id), 1)
    )


# ── UI 힌트 빌더 (시트 UI Spec 탭의 ui_type) ─────────────────────────────────


def _account_card_ui(accounts: list[dict], multi: bool = False) -> dict:
    """account_card_list — 계좌 카드 목록에서 선택하는 UI."""
    ui: dict = {
        "type": "account_card_list",
        "options": [
            {
                "account_id": a.get("account_id"),
                "account_name": a.get("account_name"),
                "balance": a.get("balance"),
            }
            for a in accounts
        ],
    }
    if multi:
        ui["multi"] = True
    return ui


def _recipient_select_ui(user_id: str) -> dict:
    """search_select — 수취인 검색/선택 UI. 조회 실패 시 options 생략."""
    try:
        options = [
            {
                "recipient_id": r.get("recipient_id"),
                "name": r.get("name"),
                "bank": r.get("bank"),
                "account_number": r.get("account_number"),
            }
            for r in _recipients(user_id)
        ]
    except BankClientError:
        options = []
    return {"type": "search_select", "options": options}


# ── 슬롯 추출 / 입력 확인 ──────────────────────────────────────────────────────


class _TransferSlots(BaseModel):
    """송금 발화에서 뽑는 슬롯 (LLM structured output용)."""

    recipient: str | None = Field(
        None,
        description=(
            "수취인 이름 또는 계좌번호. 조사(에게/한테)는 빼라 "
            "(예: '김철수'). 발화에 없으면 null."
        ),
    )
    amount: str | None = Field(
        None,
        description=(
            "송금 금액을 발화에 나온 표현 그대로 (예: '5만원', '50,000원'). "
            "숫자로 환산하지 말고 원문 그대로. 없으면 null."
        ),
    )
    from_account_hint: str | None = Field(
        None,
        description=(
            "출금할 계좌를 가리키는 단어 (예: '생활비', '입출금'). "
            "특정 계좌를 지칭하지 않으면 null."
        ),
    )


def _extract_transfer_slots_by_rule(user_input: str) -> dict:
    """규칙 기반 폴백: 정규식/키워드로 수취인·금액·계좌 힌트를 뽑는다."""
    m = _RECIPIENT_PATTERN.search(user_input)
    recipient = m.group(1) if m else None

    amount = None
    m = _AMOUNT_MAN.search(user_input)
    if m:
        amount = int(m.group(1).replace(",", "")) * 10000
    else:
        m = _AMOUNT_WON.search(user_input)
        if m:
            amount = int(m.group(1).replace(",", ""))

    from_hint = None
    m = _FROM_ACCOUNT_PATTERN.search(user_input)
    if m:
        from_hint = m.group(1)
    else:
        for keyword in _ACCOUNT_KEYWORDS:
            if keyword in user_input:
                from_hint = keyword
                break

    return {"recipient": recipient, "amount": amount, "from_account_hint": from_hint}


def extract_transfer_slots(state: dict) -> dict:
    """발화에서 수취인·금액·출금계좌 힌트를 추출한다. 항상 success.

    LLM structured output이 1순위이고, 규칙 기반(정규식/키워드)은 폴백이다:
      - LLM 호출 실패(키 없음 등) → 전부 규칙으로
      - LLM이 못 뽑은(null) 슬롯 → 그 슬롯만 규칙으로 보강
    금액은 LLM이 발화 표현 그대로("5만원") 반환하고 수치 정규화는
    verify_amount의 코드(_parse_amount)가 담당한다 — LLM이 숫자를
    지어내지 못하게 하는 원칙 (extract_balance_slots와 동일 철학).
    빈 슬롯은 None으로 두고, 이후 check_* 스텝이 되묻기로 채운다.
    """
    user_input = state.get("user_input", "")

    recipient = amount = from_hint = None
    try:
        llm = get_llm().with_structured_output(_TransferSlots)
        result = llm.invoke(
            f"다음 사용자 발화에서 송금에 필요한 슬롯을 추출해라.\n발화: {user_input}"
        )
        recipient = result.recipient or None
        amount = result.amount or None
        from_hint = result.from_account_hint or None
    except Exception:
        pass  # 아래 규칙 폴백이 전부 채운다

    # LLM이 못 뽑은 슬롯만 규칙으로 보강한다
    if recipient is None or amount is None or from_hint is None:
        fallback = _extract_transfer_slots_by_rule(user_input)
        recipient = recipient if recipient is not None else fallback["recipient"]
        amount = amount if amount is not None else fallback["amount"]
        from_hint = (
            from_hint if from_hint is not None else fallback["from_account_hint"]
        )

    return {
        "transfer.recipient": recipient,
        "transfer.amount": amount,
        "transfer.from_account": from_hint,
        "route_key": "success",
    }


def check_recipient_input(state: dict) -> dict:
    """수취인 입력 유무 확인. 없으면 ask_recipient로 되묻는다."""
    if _data(state).get("transfer.recipient"):
        return {"route_key": "exists"}
    return {
        "route_key": "missing",
        "prompt_message": "누구에게 보낼까요? 이름 또는 계좌번호를 입력해주세요.",
        "prompt_ui": _recipient_select_ui(state.get("user_id")),
    }


def resolve_recipient_input(state: dict) -> dict:
    """수취인 입력값을 등록 수취인 단건으로 해석한다."""
    user_id = state.get("user_id")
    raw = _data(state).get("transfer.recipient")
    try:
        resolved, _matches = _resolve_recipient(user_id, raw)
        if resolved:
            return {"transfer.recipient": resolved, "route_key": "resolved"}
        catalog = _recipient_catalog(user_id)
    except BankClientError:
        resolved, catalog = None, "(수취인 목록을 불러오지 못했습니다)"
    return {
        "route_key": "failed",
        "prompt_message": (
            "수취인을 하나로 확정하지 못했어요. "
            "이름 또는 계좌번호를 다시 입력해주세요.\n"
            f"등록된 수취인:\n{catalog}"
        ),
        "prompt_ui": _recipient_select_ui(user_id),
    }


def verify_recipient_account(state: dict) -> dict:
    """수취인 계좌가 송금 가능한 계좌인지 확인한다.

    ask_recipient의 답변이 문자열로 직접 들어오는 경로(resolved 직행)가
    있어 문자열도 여기서 해석한다.
    """
    user_id = state.get("user_id")
    raw = _data(state).get("transfer.recipient")
    try:
        resolved, _matches = _resolve_recipient(user_id, raw)
        if resolved and resolved.get("account_number") and resolved.get("bank"):
            return {"transfer.recipient": resolved, "route_key": "verified"}
        catalog = _recipient_catalog(user_id)
    except BankClientError:
        catalog = "(수취인 목록을 불러오지 못했습니다)"
    return {
        "route_key": "not_verified",
        "prompt_message": (
            "수취인 계좌를 확인할 수 없어요. 다시 입력해주세요.\n"
            f"등록된 수취인:\n{catalog}"
        ),
        "prompt_ui": _recipient_select_ui(user_id),
    }


def check_amount_input(state: dict) -> dict:
    """송금 금액 입력 유무 확인. 없으면 ask_amount_input으로 되묻는다."""
    if _data(state).get("transfer.amount") is not None:
        return {"route_key": "exists"}
    return {"route_key": "missing", "prompt_ui": {"type": "number_input"}}


# ── 검증 ──────────────────────────────────────────────────────────────────────

_TRANSFER_LIMIT = 50_000_000  # 1회 송금 한도
_GUARDRAIL_BLOCK = 10_000_000  # 정책 차단 기준
_GUARDRAIL_WARN = 1_000_000  # 주의 안내 기준


def verify_amount(state: dict) -> dict:
    """송금 금액을 정수로 정규화하고 한도를 확인한다."""
    raw = _data(state).get("transfer.amount")
    amount = _parse_amount(raw)
    if amount is None or amount <= 0:
        return {
            "route_key": "invalid",
            "prompt_message": (
                "금액을 확인하지 못했어요. 다시 입력해주세요 (예: 5만원)."
            ),
            "prompt_ui": {"type": "number_input"},
        }
    if amount > _TRANSFER_LIMIT:
        return {
            "transfer.amount": amount,
            "route_key": "limit_exceeded",
            "final_response": (
                f"1회 송금 한도({_TRANSFER_LIMIT:,}원)를 초과해 진행할 수 "
                f"없습니다. 요청 금액: {amount:,}원"
            ),
        }
    return {"transfer.amount": amount, "route_key": "valid"}


def verify_from_account(state: dict) -> dict:
    """출금 계좌를 확정한다 (dict 검증 / 힌트·선택 답변 해석 / 기본 계좌)."""
    try:
        user_id = state.get("user_id")
        raw = _data(state).get("transfer.from_account")
        resolved, candidates = _resolve_from_account(user_id, raw)
        if resolved:
            return {"transfer.from_account": resolved, "route_key": "verified"}
        if not candidates:
            return {
                "route_key": "failed",
                "final_response": "사용 가능한 출금 계좌가 없습니다.",
            }
        return {
            "route_key": "needs_selection",
            "prompt_message": (
                f"어느 계좌에서 송금할까요?\n{_account_options(candidates)}"
            ),
            "prompt_ui": _account_card_ui(candidates),
        }
    except Exception:
        return {
            "route_key": "failed",
            "final_response": "출금 계좌 확인 중 문제가 발생했습니다.",
        }


def check_balance(state: dict) -> dict:
    """출금 계좌의 사용 가능 잔액이 충분한지 실시간으로 확인한다."""
    try:
        user_id = state.get("user_id")
        data = _data(state)
        amount = data.get("transfer.amount")
        account = data.get("transfer.from_account") or {}
        live = _live_account(user_id, account.get("account_id"))
        if not live or not isinstance(amount, int):
            return {
                "route_key": "failed",
                "final_response": "잔액 확인 중 문제가 발생했습니다.",
            }
        if live["balance"] >= amount:
            return {"transfer.from_account": live, "route_key": "sufficient"}
        candidates = _accounts(user_id)
        return {
            "route_key": "insufficient",
            "prompt_message": (
                f"{live['account_name']} 잔액({live['balance']:,}원)이 송금 "
                f"금액({amount:,}원)보다 부족해요. 다른 계좌를 선택해주세요.\n"
                f"{_account_options(candidates)}"
            ),
            "prompt_ui": _account_card_ui(candidates),
        }
    except Exception:
        return {
            "route_key": "failed",
            "final_response": "잔액 확인 중 문제가 발생했습니다.",
        }


# ── 정책 검사 (guardrail) ─────────────────────────────────────────────────────


def run_transfer_guardrail(state: dict) -> dict:
    """송금 정책 검사: 고액 차단 / 주의 안내 / 통과."""
    amount = _data(state).get("transfer.amount") or 0
    if amount >= _GUARDRAIL_BLOCK:
        return {
            "transfer.risk": {
                "risk_level": "R5",
                "decision": "blocked",
                "reason": f"{amount:,}원 — {_GUARDRAIL_BLOCK:,}원 이상 고액 송금",
            },
            "route_key": "blocked",
            "final_response": (
                f"정책상 1회 {_GUARDRAIL_BLOCK:,}원 이상 송금은 진행할 수 "
                f"없습니다. (요청 금액: {amount:,}원)"
            ),
        }
    if amount >= _GUARDRAIL_WARN:
        return {
            "transfer.risk": {"risk_level": "R4", "decision": "warning"},
            "route_key": "warning_required",
            "prompt_message": (
                f"주의가 필요한 송금입니다. 금액: {amount:,}원\n"
                "평소보다 큰 금액이에요. 진행하려면 '확인', "
                "중단하려면 '취소'를 입력해주세요."
            ),
        }
    return {
        "transfer.risk": {"risk_level": "R2", "decision": "pass"},
        "route_key": "allowed",
    }


def run_pre_execution_guardrail(state: dict) -> dict:
    """실행 직전 검사: 승인 내용과 실행 내용 일치 + 잔액 재확인."""
    try:
        user_id = state.get("user_id")
        data = _data(state)
        approval = data.get("transfer.approval") or {}
        recipient = data.get("transfer.recipient") or {}
        account = data.get("transfer.from_account") or {}
        amount = data.get("transfer.amount")

        if (
            not approval
            or approval.get("account_number") != recipient.get("account_number")
            or approval.get("from_account_id") != account.get("account_id")
            or approval.get("amount") != amount
        ):
            return {
                "route_key": "blocked",
                "final_response": (
                    "승인한 내용과 실행 내용이 일치하지 않아 송금을 차단했습니다."
                ),
            }
        live = _live_account(user_id, account.get("account_id"))
        if not live:
            return {
                "route_key": "failed",
                "final_response": "실행 직전 검사 중 문제가 발생했습니다.",
            }
        if live["balance"] < amount:
            candidates = _accounts(user_id)
            return {
                "route_key": "insufficient_balance",
                "prompt_message": (
                    "승인 이후 잔액이 부족해졌어요. 다른 계좌를 선택해주세요.\n"
                    f"{_account_options(candidates)}"
                ),
                "prompt_ui": _account_card_ui(candidates),
            }
        return {"route_key": "allowed"}
    except Exception:
        return {
            "route_key": "failed",
            "final_response": "실행 직전 검사 중 문제가 발생했습니다.",
        }


# ── 대화형 tool (interrupt 호출) ──────────────────────────────────────────────


def transfer_warning(state: dict) -> dict:
    """송금 주의 안내를 보여주고 사용자 확인을 받는다 (interrupt)."""
    prompt = state.get("prompt_message") or (
        "주의가 필요한 송금입니다. 진행하려면 '확인', 중단하려면 '취소'를 입력해주세요."
    )
    amount = _data(state).get("transfer.amount")
    reply = interrupt(
        {
            "prompt": prompt,
            "prompt_for": "transfer.warning_confirm",
            "ui": {
                "type": "confirm_modal",
                "variant": "warning",
                "display": {"amount": amount},
                "actions": ["확인", "취소"],
            },
        }
    )

    route = _parse_warning_reply(str(reply))
    updates: dict = {"route_key": route, "prompt_message": None, "prompt_ui": None}
    if route == "cancelled":
        updates["final_response"] = "송금을 취소했습니다."
    return updates


def create_approval(state: dict) -> dict:
    """송금 승인 카드를 보여주고 승인/취소/수정 답변을 받는다 (interrupt).

    approved 시 승인 요약(transfer.approval)을 기록해 실행 직전 검사가
    승인 내용과 실제 실행 내용의 일치를 대조할 수 있게 한다.
    """
    data = _data(state)
    recipient = data.get("transfer.recipient") or {}
    account = data.get("transfer.from_account") or {}
    amount = data.get("transfer.amount") or 0

    card = (
        "[송금 확인]\n"
        f"  받는 분    : {recipient.get('name', '?')} "
        f"({recipient.get('bank', '?')} {recipient.get('account_number', '?')})\n"
        f"  보내는 계좌: {account.get('account_name', '?')}\n"
        f"  금액       : {amount:,}원\n"
        "진행하려면 '승인', 중단하려면 '취소',\n"
        "수정하려면 '수취인 수정' / '금액 수정' / '계좌 수정'을 입력해주세요."
    )
    reply = interrupt(
        {
            "prompt": card,
            "prompt_for": "transfer.approval_decision",
            "ui": {
                "type": "confirm_modal",
                "display": {
                    "recipient_name": recipient.get("name"),
                    "bank": recipient.get("bank"),
                    "account_number": recipient.get("account_number"),
                    "from_account_name": account.get("account_name"),
                    "amount": amount,
                },
                "actions": [
                    "송금하기",
                    "취소",
                    "수취인 수정",
                    "금액 수정",
                    "계좌 수정",
                ],
            },
        }
    )

    route = _parse_approval_reply(str(reply))
    updates: dict = {"route_key": route, "prompt_message": None, "prompt_ui": None}
    if route == "approved":
        updates["transfer.approval"] = {
            "recipient_id": recipient.get("recipient_id"),
            "account_number": recipient.get("account_number"),
            "from_account_id": account.get("account_id"),
            "amount": amount,
        }
    elif route == "cancelled":
        updates["final_response"] = (
            "송금을 취소했습니다."
            if _is_cancel(str(reply))
            else "확인할 수 없는 답변이라 송금을 취소했습니다. 다시 시도해주세요."
        )
    elif route == "edit_amount":
        updates["transfer.amount"] = None
        updates["prompt_message"] = "새 송금 금액을 입력해주세요 (예: 3만원)."
        updates["prompt_ui"] = {"type": "number_input"}
    elif route == "edit_recipient":
        updates["transfer.recipient"] = None
        updates["prompt_message"] = "새 수취인을 입력해주세요 (이름 또는 계좌번호)."
        updates["prompt_ui"] = _recipient_select_ui(state.get("user_id"))
    elif route == "edit_from_account":
        updates["transfer.from_account"] = None
        updates["prompt_message"] = "어느 계좌에서 송금할까요?"
        try:
            updates["prompt_ui"] = _account_card_ui(_accounts(state.get("user_id")))
        except BankClientError:
            pass
    return updates


def request_user_authentication(state: dict) -> dict:
    """송금 실행 전 본인 인증을 요청한다 (interrupt, mock 인증)."""
    reply = interrupt(
        {
            "prompt": (
                "본인 인증을 진행해주세요 (지문 / Face ID / 비밀번호). "
                "완료 후 '인증완료'를 입력해주세요."
            ),
            "prompt_for": "transfer.auth_result",
            # auth_request는 시트 UI Spec에 없는 타입 — 시트 추가 요청 대상
            "ui": {
                "type": "auth_request",
                "methods": ["지문", "Face ID", "비밀번호"],
                "actions": ["인증완료", "취소"],
            },
        }
    )
    route = _parse_auth_reply(str(reply))
    updates: dict = {"route_key": route, "prompt_message": None, "prompt_ui": None}
    if route == "not_authenticated":
        updates["final_response"] = (
            "본인 인증이 완료되지 않아 송금을 진행할 수 없습니다."
        )
    return updates


# ── 송금 실행 / 응답 ──────────────────────────────────────────────────────────


def transfer_money(state: dict) -> dict:
    """Fake Money 송금을 실행한다. 원장 차감은 BankClient가 담당한다."""
    user_id = state.get("user_id")
    data = _data(state)
    recipient = data.get("transfer.recipient") or {}
    account = data.get("transfer.from_account") or {}
    amount = data.get("transfer.amount")

    if not recipient.get("recipient_id") or not isinstance(amount, int):
        return {
            "route_key": "failed",
            "final_response": "송금 처리 중 문제가 발생했습니다.",
        }

    try:
        live = _live_account(user_id, account.get("account_id"))
        if not live:
            return {
                "route_key": "failed",
                "final_response": "송금 처리 중 문제가 발생했습니다.",
            }
        if live["balance"] < amount:
            return {
                "route_key": "failed",
                "final_response": "잔액이 부족해 송금하지 못했습니다.",
            }
        result = get_bank_client().transfer(
            user_id=user_id,
            from_account_id=live["account_id"],
            to_recipient_id=recipient["recipient_id"],
            amount=amount,
            memo=data.get("transfer.memo"),
        )
    except BankClientError:
        return {
            "route_key": "failed",
            "final_response": "송금 처리 중 문제가 발생했습니다.",
        }

    return {
        "transfer.transfer_result": {
            "transaction_id": result.get("transaction_id"),
            "from_account_id": live["account_id"],
            "to_recipient_id": recipient["recipient_id"],
            "to_recipient_name": recipient.get("name"),
            "amount": amount,
            "status": result.get("status", "completed"),
        },
        "route_key": "success",
    }


def generate_transfer_response(state: dict) -> dict:
    """송금 결과를 사용자 응답 문장으로 만든다 (결정적)."""
    result = _data(state).get("transfer.transfer_result") or {}
    if result.get("status") != "completed":
        return {
            "route_key": "failed",
            "final_response": "송금 결과를 확인하지 못했습니다.",
        }
    return {
        "route_key": "success",
        "final_response": (
            f"{result['to_recipient_name']}님에게 {result['amount']:,}원을 "
            f"송금했습니다. 거래번호: {result['transaction_id']}"
        ),
    }


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
    # 원장 서비스에도 best-effort 전송 — 실패해도 사용자 흐름을 막지 않는다
    # (시트 규칙: "로그 실패는 사용자 흐름을 막지 않는다")
    try:
        get_bank_client().post_audit_log(
            event_type="workflow_completed",
            workflow_id=state.get("workflow_id"),
            tool_id="write_audit_log",
            result={
                "log_id": log_id,
                "final_response": state.get("final_response"),
            },
        )
    except Exception:  # noqa: BLE001 - 감사 로그 전송 실패는 흐름 무영향
        pass

    return {"log_id": log_id, "logs": logs + [entry], "route_key": "logged"}
