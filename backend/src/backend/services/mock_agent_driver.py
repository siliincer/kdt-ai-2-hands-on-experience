"""mock 에이전트 드라이버.

실제 Agent(LangGraph)가 스텁이라, /chat·/approve 가 이 드라이버를 백그라운드로 돌려
agent:stream:{chat_session_id} 에 status/tool_call/need_approval/done 을 XADD 한다.
→ FE(assistant-ui)의 스트리밍·confirm(HITL) 루프를 에이전트 없이 검증할 수 있다.

실제 Agent 연동 시 이 파일을 걷어내고, Agent 가 웹훅(POST /webhooks/agent) 또는
직접 XADD 로 동일 이벤트를 보내면 된다.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from ..db.postgres import AsyncSessionLocal
from ..db.redis import stream_pool
from ..models.confirmation import ConfirmationOperation
from ..repository.confirmation_repository import get_confirmation_by_id
from ..schemas.sse import AgentStreamEvent, AgentStreamEventType
from .agent_stream_producer import publish_agent_event
from .auth_context_service import create_for_confirmation
from .confirmation_service import create_pending
from .execution_context_service import resolve_context
from .mock.hitl_fixtures import (
    ALIAS_TARGET_ACCOUNT,
    BALANCE_ACCOUNTS,
    UI_ACCOUNT_ALIAS_INPUT,
    UI_BALANCE_ACCOUNT_SELECTION,
    UI_EXTERNAL_FROM_ACCOUNT,
    UI_EXTERNAL_TRANSFER_AUTH,
    UI_EXTERNAL_TRANSFER_AUTH_RETRY,
    UI_PERIOD_SELECTION,
    UI_RECIPIENT_SELECT,
    UI_SUMMARY_ACCOUNT_SELECTION,
    UI_SUMMARY_TYPE_SELECTION,
    UI_TRANSACTION_ACCOUNT_SELECTION,
    UI_TRANSFER_AMOUNT_INPUT,
    build_account_card_payload,
    build_account_list,
    build_alias_confirm_view,
    build_alias_setting_result,
    build_amount_input_view,
    build_amount_summary,
    build_auth_request_view,
    build_auth_retry_view,
    build_balance_result,
    build_external_transfer_confirm_view,
    build_from_account_view,
    build_period_input_view,
    build_recipient_select_view,
    build_summary_type_view,
    build_transaction_list,
    build_transfer_result,
    find_recipient,
)
from .pending_input_service import register_pending_input

logger = logging.getLogger(__name__)

# confirm_modal(설정 변경) component 값 — run_after_approval 이 실제 Confirmation
# 생명주기로 분기하는 데 쓴다. 레거시 송금/자동이체와 구분한다.
_SETTING_COMPONENTS = frozenset({"account_alias", "default_account"})

# 타인송금은 여러 입력을 순차로 모아 Confirmation 을 만든다. mock 은 실 Agent 의
# LangGraph state 를 대신해 chat_session 별 진행 상태를 인메모리로 보관한다(단일 워커
# 데모 전제, 실 Agent 연동 시 제거). key=str(chat_session_id).
_WF_STATE: dict[str, dict] = {}

_STEP_DELAY_SECONDS = 0.5

# 송금 의도로 볼 키워드
_TRANSFER_KEYWORDS = ("송금", "보내", "이체", "transfer")

# 자동이체(정기결제) 등록 의도 키워드. "이체"를 포함하므로 송금보다 먼저 검사한다.
_AUTOTRANSFER_KEYWORDS = (
    "자동이체",
    "정기이체",
    "정기결제",
    "정기 결제",
    "autotransfer",
)

# 읽기전용 카드 의도 → component 키 (앞쪽 우선 매칭)
_COMPONENT_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("잔액", "자산", "balance"), "balance"),
    (("소비", "지출", "spending"), "spending"),
    (("거래 내역", "거래내역", "내역", "transactions"), "transactions"),
    (("예산", "구독", "budget"), "budget"),
    (("카드", "청구서", "cards"), "cards"),
]

# component 별 안내 문구(status/component/done 텍스트)
_COMPONENT_MESSAGES: dict[str, tuple[str, str]] = {
    "balance": ("자산 현황을 불러왔어요.", "다른 도움이 필요하시면 말씀해 주세요."),
    "spending": (
        "이번 달 소비 분석을 준비했어요.",
        "카테고리를 눌러 상세 내역을 볼 수 있어요.",
    ),
    "transactions": ("거래 내역을 불러왔어요.", "월을 선택해 기간별로 확인해 보세요."),
    "budget": ("예산 현황을 불러왔어요.", "예산과 구독을 관리해 보세요."),
    "cards": ("보유하신 카드를 불러왔어요.", "카드를 눌러 자세히 확인해 보세요."),
}

# 파싱 실패 시 사용할 샘플(스크린샷 기준)
_SAMPLE_ARGS = {
    "name": "김철수",
    "bank": "하나은행",
    "account": "110-123-456789",
    "amount": "30000",
    "time": "지금 바로",
}

# 자동이체 confirm 폼 프리필 샘플(파싱 실패 시)
_AUTOTRANSFER_SAMPLE_ARGS = {
    "account": "우리은행 1002-345-678901",
    "amount": "200000",
    "day": "매월 25일",
}


# 계좌 별칭 변경 의도 키워드(wf_set_account_alias).
_ALIAS_KEYWORDS = ("별칭", "계좌 이름", "계좌명", "계좌 별명", "alias")

# 계좌 목록 조회 의도(wf_account_list).
_ACCOUNT_LIST_KEYWORDS = ("계좌 목록", "계좌목록", "보유 계좌", "내 계좌", "계좌 보여")

# 기간 합계 조회 의도(wf_period_amount_summary). "얼마"류 지출·수입 합계.
_SUMMARY_KEYWORDS = ("합계", "얼마 썼", "얼마 벌", "지출 합", "수입 합", "총 지출")


def _is_alias_intent(message: str) -> bool:
    return any(keyword in message for keyword in _ALIAS_KEYWORDS)


def _is_account_list_intent(message: str) -> bool:
    return any(keyword in message for keyword in _ACCOUNT_LIST_KEYWORDS)


def _is_summary_intent(message: str) -> bool:
    return any(keyword in message for keyword in _SUMMARY_KEYWORDS)


def _is_autotransfer_intent(message: str) -> bool:
    return any(keyword in message for keyword in _AUTOTRANSFER_KEYWORDS)


def _is_transfer_intent(message: str) -> bool:
    return any(keyword in message for keyword in _TRANSFER_KEYWORDS)


def _match_component(message: str) -> str | None:
    """읽기전용 카드 의도면 component 키를 반환."""
    for keywords, component in _COMPONENT_KEYWORDS:
        if any(keyword in message for keyword in keywords):
            return component
    return None


def _extract_transfer_args(message: str) -> dict[str, str]:
    """메시지에서 송금 파라미터를 가볍게 파싱(목). 실패 필드는 샘플로 채운다."""
    args = dict(_SAMPLE_ARGS)

    # 금액: "30,000원" / "3만원" 대략 처리 → 숫자만
    amount_match = re.search(r"([\d,]{1,20})\s*원", message)
    if amount_match:
        args["amount"] = amount_match.group(1).replace(",", "")

    # 계좌번호: 숫자/하이픈 6자리 이상
    account_match = re.search(r"\d[\d-]{5,}", message)
    if account_match:
        args["account"] = account_match.group(0)

    return args


def _extract_autotransfer_args(message: str) -> dict[str, str]:
    """메시지에서 자동이체 파라미터를 가볍게 파싱(목). 실패 필드는 샘플로 채운다."""
    args = dict(_AUTOTRANSFER_SAMPLE_ARGS)

    amount_match = re.search(r"([\d,]{1,20})\s*원", message)
    if amount_match:
        args["amount"] = amount_match.group(1).replace(",", "")

    # 이체일: "매월 25일" / "25일"
    day_match = re.search(r"(매월\s*)?(\d{1,2})\s*일", message)
    if day_match:
        args["day"] = f"매월 {day_match.group(2)}일"

    return args


async def _emit(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    event_type: AgentStreamEventType,
    content: str,
    *,
    approval_id: str | None = None,
    metadata: dict | None = None,
    delay: bool = True,
) -> None:
    if delay:
        await asyncio.sleep(_STEP_DELAY_SECONDS)
    await publish_agent_event(
        redis_stream,
        chat_session_id,
        AgentStreamEvent(
            event_type=event_type,
            content=content,
            approval_id=approval_id,
            metadata=metadata,
        ),
    )


async def _register_pending_input(
    chat_session_id: UUID,
    input_request_id: str,
    ui_contract_id: str,
    ui_type: str,
    execution_context_id: UUID | None,
    agent_thread_id: str | None,
) -> None:
    """need_input 발행 전에 대기 행을 DB 에 영속한다(계약 1.4·1.5).

    실 Agent 는 Webhook 경로로 영속되지만, in-process mock 은 자체 세션으로 등록한다.
    """
    async with AsyncSessionLocal() as session:
        await register_pending_input(
            session,
            chat_session_id=chat_session_id,
            input_request_id=input_request_id,
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
            execution_context_id=execution_context_id,
            agent_thread_id=agent_thread_id,
        )


async def run_initial_turn(
    chat_session_id: UUID,
    message: str,
    execution_context_id: UUID | None = None,
    agent_thread_id: str | None = None,
) -> None:
    """사용자 메시지에 대한 첫 턴을 스트림에 발행한다.

    송금 의도면 need_approval(confirm 카드)까지 발행하고 멈춘다(승인 대기).
    잔액 의도면 need_input(계좌 선택)까지 발행하고 멈춘다(wf_balance_inquiry 입력 대기).
    그 외에는 간단한 답변 후 done.
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        # 계좌 별칭 변경(wf_set_account_alias): 별칭 입력(text_input)부터 시작.
        if _is_alias_intent(message):
            await _run_alias_input(
                redis_stream, chat_session_id, execution_context_id, agent_thread_id
            )
            return

        # 자동이체는 "이체"를 포함하므로 송금보다 먼저 검사한다.
        if _is_autotransfer_intent(message):
            args = _extract_autotransfer_args(message)
            approval_id = uuid4().hex
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.STATUS,
                "자동이체 등록을 도와드릴게요. 정보를 확인해 주세요.",
                delay=False,
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.NEED_APPROVAL,
                "아래 내용으로 자동이체를 등록할까요? 각 항목을 수정할 수 있어요.",
                approval_id=approval_id,
                metadata={"tool": "autotransfer", "args": args},
            )
            # 승인 대기 — done 을 보내지 않고 종료(스트림은 열린 채 유지)
            return

        if _is_transfer_intent(message):
            # 타인송금(wf_external_transfer): 수취인 선택(need_input)부터 시작.
            await _run_external_recipient(
                redis_stream, chat_session_id, execution_context_id
            )
            return

        # 기간 합계(wf_period_amount_summary): 계좌 선택부터 시작.
        if _is_summary_intent(message):
            await _run_query_account_selection(
                redis_stream, chat_session_id, execution_context_id, "summary"
            )
            return

        # 계좌 목록(wf_account_list): 입력 없이 결과만 발행.
        if _is_account_list_intent(message):
            await _run_account_list(redis_stream, chat_session_id)
            return

        component = _match_component(message)
        if component == "balance":
            # 잔액 조회는 계약 wf_balance_inquiry: 계좌 선택(need_input) → 잔액 결과.
            await _run_balance_account_selection(
                redis_stream, chat_session_id, execution_context_id, agent_thread_id
            )
            return

        if component == "transactions":
            # 거래내역(wf_transaction_history): 계좌 선택 → 기간 → 거래 목록.
            await _run_query_account_selection(
                redis_stream, chat_session_id, execution_context_id, "transaction"
            )
            return

        if component is not None:
            # 읽기전용 카드: 데이터는 싣지 않고 렌더 시그널만(ADR-002).
            # FE 가 UI Data API 로 데이터를 별도 fetch 한다.
            component_text, done_text = _COMPONENT_MESSAGES[component]
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.STATUS,
                "정보를 조회하고 있어요...",
                delay=False,
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.COMPONENT,
                component_text,
                metadata={"component": component},
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.DONE,
                done_text,
            )
            return

        # 일반 대화(목)
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.STATUS,
            "생각하고 있어요...",
            delay=False,
        )
        answer_chunks = (
            "무엇을 ",
            "도와드릴까요? ",
            "송금, 잔액 조회, ",
            "거래내역, 예산관리, 잔액조회, "
            "자동이체등록, 카드관리, "
            "소비 분석을 할 수 있어요.",
        )
        for chunk in answer_chunks:
            await _emit(
                redis_stream, chat_session_id, AgentStreamEventType.TOKEN, chunk
            )
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "무엇이든 말씀해 주세요.",
        )
    finally:
        await redis_stream.aclose()


async def _run_balance_account_selection(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    execution_context_id: UUID | None,
    agent_thread_id: str | None,
) -> None:
    """wf_balance_inquiry: 잔액 조회 계좌 선택을 need_input 으로 요청한다(계약 5.3)."""
    input_request_id = f"input_balance_{uuid4().hex[:12]}"
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "잔액을 조회할 계좌를 확인하고 있어요...",
        delay=False,
    )
    # need_input 발행 전에 대기 행을 먼저 만든다(FE 즉시 제출 대비, 계약 1.5).
    await _register_pending_input(
        chat_session_id,
        input_request_id,
        UI_BALANCE_ACCOUNT_SELECTION,
        "account_card_list",
        execution_context_id,
        agent_thread_id,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.NEED_INPUT,
        "잔액을 조회할 계좌를 선택해 주세요.",
        metadata={
            "input_request_id": input_request_id,
            "ui_contract_id": UI_BALANCE_ACCOUNT_SELECTION,
            "ui": {
                "type": "account_card_list",
                "payload": {
                    "title": "잔액을 조회할 계좌를 선택해 주세요.",
                    "accounts": BALANCE_ACCOUNTS,
                    "actions": ["select", "cancel"],
                },
            },
        },
    )
    # 입력 대기 — done 을 보내지 않고 종료(스트림은 열린 채 유지)


async def _run_alias_input(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    execution_context_id: UUID | None,
    agent_thread_id: str | None,
) -> None:
    """wf_set_account_alias: 새 별칭을 text_input 으로 입력받는다(계약 3.1)."""
    input_request_id = f"input_alias_{uuid4().hex[:12]}"
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "계좌 별칭 변경을 도와드릴게요.",
        delay=False,
    )
    await _register_pending_input(
        chat_session_id,
        input_request_id,
        UI_ACCOUNT_ALIAS_INPUT,
        "text_input",
        execution_context_id,
        agent_thread_id,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.NEED_INPUT,
        "새 계좌 별칭을 입력해 주세요.",
        metadata={
            "input_request_id": input_request_id,
            "ui_contract_id": UI_ACCOUNT_ALIAS_INPUT,
            "ui": {
                "type": "text_input",
                "payload": {
                    "title": "새 계좌 별칭을 입력해 주세요.",
                    "description": (
                        f"{ALIAS_TARGET_ACCOUNT['bank_name']} "
                        f"{ALIAS_TARGET_ACCOUNT['masked_account_number']}"
                    ),
                    "validation": {"required": True, "max_length": 30},
                    "actions": ["submit", "cancel"],
                },
            },
        },
    )
    # 입력 대기 — done 을 보내지 않고 종료


async def _create_alias_confirmation(
    execution_context_id: UUID, alias: str
) -> str | None:
    """별칭 변경 Confirmation 을 실제로 생성한다(승인 생명주기, 계약 14장).

    fixed_data 에 계좌·별칭을 고정해 두면, 승인 후 결과 단계에서 이 값을 그대로
    복원해 setting_result 를 만든다(교차 스텝 상태를 Confirmation 이 대신한다).
    """
    async with AsyncSessionLocal() as session:
        context = await resolve_context(session, str(execution_context_id))
        confirmation = await create_pending(
            session,
            context,
            ConfirmationOperation.ACCOUNT_ALIAS_CHANGE,
            fixed_data={"account": ALIAS_TARGET_ACCOUNT, "alias": alias},
        )
        return str(confirmation.id)


async def _load_confirmation(
    confirmation_id: str,
) -> tuple[dict | None, UUID | None]:
    """Confirmation 의 fixed_data 와 execution_context_id 를 읽는다(결과·재요청용)."""
    try:
        conf_uuid = UUID(confirmation_id)
    except ValueError:
        return None, None
    async with AsyncSessionLocal() as session:
        confirmation = await get_confirmation_by_id(session, conf_uuid)
        if confirmation is None:
            return None, None
        return dict(confirmation.fixed_data), confirmation.execution_context_id


async def run_after_input(
    chat_session_id: UUID,
    ui_contract_id: str,
    value: dict,
    execution_context_id: UUID | None = None,
) -> None:
    """일반 입력·선택 대기 회신 이후의 후속 턴을 발행한다(UI-HITL 계약 1.5).

    `ui_contract_id` 로 어떤 워크플로우를 이어갈지 분기한다.
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        if ui_contract_id == UI_BALANCE_ACCOUNT_SELECTION:
            await _run_balance_result(redis_stream, chat_session_id, value)
        elif ui_contract_id == UI_ACCOUNT_ALIAS_INPUT:
            await _run_alias_confirm(
                redis_stream, chat_session_id, value, execution_context_id
            )
        elif ui_contract_id == UI_RECIPIENT_SELECT:
            await _run_external_after_recipient(
                redis_stream, chat_session_id, value, execution_context_id
            )
        elif ui_contract_id == UI_EXTERNAL_FROM_ACCOUNT:
            await _run_external_after_from_account(
                redis_stream, chat_session_id, value, execution_context_id
            )
        elif ui_contract_id == UI_TRANSFER_AMOUNT_INPUT:
            await _run_external_after_amount(
                redis_stream, chat_session_id, value, execution_context_id
            )
        elif ui_contract_id == UI_EXTERNAL_TRANSFER_AUTH_RETRY:
            await _run_external_auth_retry(
                redis_stream, chat_session_id, value, execution_context_id
            )
        elif ui_contract_id in (
            UI_TRANSACTION_ACCOUNT_SELECTION,
            UI_SUMMARY_ACCOUNT_SELECTION,
        ):
            await _run_query_after_account(
                redis_stream, chat_session_id, value, execution_context_id
            )
        elif ui_contract_id == UI_PERIOD_SELECTION:
            await _run_query_after_period(
                redis_stream, chat_session_id, value, execution_context_id
            )
        elif ui_contract_id == UI_SUMMARY_TYPE_SELECTION:
            await _run_summary_result(redis_stream, chat_session_id, value)
        else:
            # 아직 워크플로우가 없는 계약: 브리지 확인용 플레이스홀더(다음 Slice 교체).
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.DONE,
                "입력을 반영했어요.",
                delay=False,
            )
    finally:
        await redis_stream.aclose()


async def _run_alias_confirm(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
    execution_context_id: UUID | None,
) -> None:
    """별칭 입력 후 confirm_modal(승인 대기)을 발행한다(계약 3.7)."""
    if value.get("alias_input_outcome") != "submitted":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "별칭 변경을 취소했어요.",
            delay=False,
        )
        return

    alias = str(value.get("alias") or "").strip()
    if not alias or execution_context_id is None:
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "별칭을 확인하지 못해 취소했어요.",
            delay=False,
        )
        return

    confirmation_id = await _create_alias_confirmation(execution_context_id, alias)
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.NEED_APPROVAL,
        "아래 내용으로 계좌 별칭을 변경할까요?",
        approval_id=confirmation_id,
        metadata={"tool": "modal", "args": build_alias_confirm_view(alias)},
    )
    # 승인 대기 — done 을 보내지 않고 종료


# ── wf_external_transfer (계약 5.9) ───────────────────────────────────────────


async def _emit_need_input(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    execution_context_id: UUID | None,
    ui_contract_id: str,
    ui_type: str,
    content: str,
    payload: dict,
) -> None:
    """need_input 대기 행 등록 + 이벤트 발행 공통 헬퍼."""
    input_request_id = f"input_{ui_type}_{uuid4().hex[:8]}"
    await _register_pending_input(
        chat_session_id,
        input_request_id,
        ui_contract_id,
        ui_type,
        execution_context_id,
        None,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.NEED_INPUT,
        content,
        metadata={
            "input_request_id": input_request_id,
            "ui_contract_id": ui_contract_id,
            "ui": {"type": ui_type, "payload": payload},
        },
    )


async def _external_cancel(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    message: str = "송금을 취소했어요.",
) -> None:
    _WF_STATE.pop(str(chat_session_id), None)
    await _emit(
        redis_stream, chat_session_id, AgentStreamEventType.DONE, message, delay=False
    )


async def _run_external_recipient(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    execution_context_id: UUID | None,
) -> None:
    """타인송금 1단계: 수취인 선택(recipient_select)."""
    _WF_STATE[str(chat_session_id)] = {}
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "타인송금을 도와드릴게요.",
        delay=False,
    )
    await _emit_need_input(
        redis_stream,
        chat_session_id,
        execution_context_id,
        UI_RECIPIENT_SELECT,
        "recipient_select",
        "받는 분을 선택해 주세요.",
        build_recipient_select_view(),
    )


async def _run_external_after_recipient(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
    execution_context_id: UUID | None,
) -> None:
    """수취인 확정 → 출금 계좌 선택으로 진행."""
    if value.get("recipient_selection_outcome") != "selected":
        await _external_cancel(redis_stream, chat_session_id)
        return

    recipient = None
    to_recipient_id = value.get("to_recipient_id")
    candidate_id = value.get("to_recipient_candidate_id")
    if to_recipient_id:
        recipient = find_recipient(str(to_recipient_id))
    elif candidate_id:
        # 신규 검증 후보(mock): 표시 정보는 최소만 둔다.
        recipient = {
            "name": "신규 수취인",
            "bank_name": None,
            "masked_account_number": "",
        }
    if recipient is None:
        await _external_cancel(
            redis_stream, chat_session_id, "수취인을 확인하지 못해 취소했어요."
        )
        return

    state = _WF_STATE.setdefault(str(chat_session_id), {})
    state["recipient"] = recipient
    await _emit_need_input(
        redis_stream,
        chat_session_id,
        execution_context_id,
        UI_EXTERNAL_FROM_ACCOUNT,
        "account_card_list",
        "출금할 계좌를 선택해 주세요.",
        build_from_account_view(),
    )


async def _run_external_after_from_account(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
    execution_context_id: UUID | None,
) -> None:
    """출금 계좌 확정 → 금액 입력으로 진행."""
    account_ids = value.get("account_ids") or []
    if value.get("account_selection_outcome") != "selected" or not account_ids:
        await _external_cancel(redis_stream, chat_session_id)
        return

    state = _WF_STATE.setdefault(str(chat_session_id), {})
    state["from_account_id"] = str(account_ids[0])
    await _emit_need_input(
        redis_stream,
        chat_session_id,
        execution_context_id,
        UI_TRANSFER_AMOUNT_INPUT,
        "number_input",
        "송금 금액을 입력해 주세요.",
        build_amount_input_view(),
    )


async def _run_external_after_amount(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
    execution_context_id: UUID | None,
) -> None:
    """금액 확정 → Confirmation 생성 후 confirm_modal(승인 대기)."""
    if value.get("amount_input_outcome") != "submitted":
        await _external_cancel(redis_stream, chat_session_id)
        return
    if execution_context_id is None:
        await _external_cancel(
            redis_stream, chat_session_id, "송금 정보를 확인하지 못해 취소했어요."
        )
        return

    state = _WF_STATE.setdefault(str(chat_session_id), {})
    state["amount"] = value.get("amount")
    fixed_data = {
        "from_account_id": state.get("from_account_id"),
        "recipient": state.get("recipient"),
        "amount": state.get("amount"),
    }
    confirmation_id = await _create_external_confirmation(
        execution_context_id, fixed_data
    )
    state["confirmation_id"] = confirmation_id
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.NEED_APPROVAL,
        "송금 내용을 확인해 주세요.",
        approval_id=confirmation_id,
        metadata={
            "tool": "modal",
            "args": build_external_transfer_confirm_view(fixed_data),
        },
    )


async def _create_external_confirmation(
    execution_context_id: UUID, fixed_data: dict
) -> str:
    """타인송금 Confirmation 을 생성한다(EXTERNAL_TRANSFER, fixed_data 고정)."""
    async with AsyncSessionLocal() as session:
        context = await resolve_context(session, str(execution_context_id))
        confirmation = await create_pending(
            session,
            context,
            ConfirmationOperation.EXTERNAL_TRANSFER,
            fixed_data=fixed_data,
        )
        return str(confirmation.id)


async def _run_external_after_approval(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
) -> None:
    """송금 confirm_modal 결과 → 인증 요청/재입력/취소."""
    if decision == "cancelled":
        await _external_cancel(redis_stream, chat_session_id)
        return

    _fixed_data, execution_context_id = await _load_confirmation(approval_id)
    if decision == "change_requested":
        # 수정: 기존 Confirmation 은 폐기됐고, 금액부터 재입력한다(recipient·계좌 유지).
        await _emit_need_input(
            redis_stream,
            chat_session_id,
            execution_context_id,
            UI_TRANSFER_AMOUNT_INPUT,
            "number_input",
            "송금 금액을 다시 입력해 주세요.",
            build_amount_input_view(),
        )
        return

    # approve → 추가 인증(auth_request) 발행.
    auth_context_id = await _create_auth_context(execution_context_id, approval_id)
    state = _WF_STATE.setdefault(str(chat_session_id), {})
    state["auth_context_id"] = auth_context_id
    await _emit_auth_request(redis_stream, chat_session_id, auth_context_id)


async def _create_auth_context(
    execution_context_id: UUID | None, confirmation_id: str
) -> str | None:
    """승인된 Confirmation 에 대한 인증 Context 를 생성한다(계약 15장)."""
    if execution_context_id is None:
        return None
    async with AsyncSessionLocal() as session:
        context = await resolve_context(session, str(execution_context_id))
        confirmation = await get_confirmation_by_id(session, UUID(confirmation_id))
        if confirmation is None:
            return None
        auth_context = await create_for_confirmation(session, context, confirmation)
        return str(auth_context.id)


async def _emit_auth_request(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    auth_context_id: str | None,
) -> None:
    """authentication_required 발행(계약 3.8). 인증은 auth_context_id 로 매칭한다.

    일반 입력(pending_input)과 달리, 인증 대기는 auth_context 행 자체가 상태를 가지므로
    pending_input 을 만들지 않는다. FE 는 비밀번호를 /agent/authenticate 로 제출한다.
    """
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.AUTHENTICATION_REQUIRED,
        "송금을 계속하려면 비밀번호를 다시 입력해 주세요.",
        metadata={
            "auth_context_id": auth_context_id,
            "ui_contract_id": UI_EXTERNAL_TRANSFER_AUTH,
            "ui": {"type": "auth_request", "payload": build_auth_request_view()},
        },
    )


async def run_after_auth(
    chat_session_id: UUID,
    auth_status: str,
) -> None:
    """Backend 인증 검증 결과 이후의 후속 턴(계약 3.8·4.5).

    verified → 송금 완료(transfer_result). failed → 재인증 선택(option_select).
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        state = _WF_STATE.setdefault(str(chat_session_id), {})
        confirmation_id = state.get("confirmation_id")
        fixed_data, execution_context_id = (
            await _load_confirmation(confirmation_id)
            if confirmation_id
            else (None, None)
        )

        if auth_status == "verified":
            transaction_id = f"txn_{uuid4().hex[:12]}"
            completed_at = datetime.now(timezone.utc).isoformat()
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.STATUS,
                "송금을 처리하고 있어요...",
                delay=False,
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.COMPONENT,
                "송금을 완료했어요.",
                metadata={
                    "component": "transfer_result",
                    "params": build_transfer_result(
                        fixed_data or {}, transaction_id, completed_at
                    ),
                },
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.DONE,
                "송금이 완료되었어요.",
            )
            _WF_STATE.pop(str(chat_session_id), None)
        else:
            await _emit_need_input(
                redis_stream,
                chat_session_id,
                execution_context_id,
                UI_EXTERNAL_TRANSFER_AUTH_RETRY,
                "option_select",
                "인증에 실패했어요.",
                build_auth_retry_view(),
            )
    finally:
        await redis_stream.aclose()


async def _run_external_auth_retry(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
    execution_context_id: UUID | None,
) -> None:
    """재인증 선택(option_select) → 새 인증 요청 또는 취소."""
    state = _WF_STATE.setdefault(str(chat_session_id), {})
    if (
        value.get("option_selection_outcome") != "selected"
        or value.get("option") != "retry"
    ):
        await _external_cancel(redis_stream, chat_session_id)
        return

    confirmation_id = state.get("confirmation_id")
    if not confirmation_id:
        await _external_cancel(
            redis_stream, chat_session_id, "송금 정보를 확인하지 못해 취소했어요."
        )
        return
    _fixed_data, ctx_id = await _load_confirmation(confirmation_id)
    auth_context_id = await _create_auth_context(ctx_id, confirmation_id)
    state["auth_context_id"] = auth_context_id
    await _emit_auth_request(redis_stream, chat_session_id, auth_context_id)


# ── 조회 워크플로우 (계약 5.2·5.4·5.5) ────────────────────────────────────────


async def _run_account_list(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
) -> None:
    """wf_account_list: 입력 없이 계좌 목록 결과만 발행(계약 5.2)."""
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "계좌 목록을 불러오고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.COMPONENT,
        "계좌 목록을 불러왔어요.",
        metadata={"component": "account_list", "params": build_account_list()},
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        "다른 도움이 필요하시면 말씀해 주세요.",
    )


async def _run_query_account_selection(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    execution_context_id: UUID | None,
    workflow: str,
) -> None:
    """거래내역·기간합계 공통: 조회 계좌 선택(account_card_list)부터 시작.

    두 워크플로우는 같은 UI-PERIOD-SELECTION 을 쓰므로 활성 workflow 를 상태에 기록해
    이후 분기한다(계약 5.4·5.5).
    """
    _WF_STATE[str(chat_session_id)] = {"wf": workflow}
    ui_contract_id = (
        UI_TRANSACTION_ACCOUNT_SELECTION
        if workflow == "transaction"
        else UI_SUMMARY_ACCOUNT_SELECTION
    )
    title = "조회할 계좌를 선택해 주세요."
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "조회할 계좌를 확인하고 있어요...",
        delay=False,
    )
    await _emit_need_input(
        redis_stream,
        chat_session_id,
        execution_context_id,
        ui_contract_id,
        "account_card_list",
        title,
        build_account_card_payload(title),
    )


async def _run_query_after_account(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
    execution_context_id: UUID | None,
) -> None:
    """조회 계좌 확정 → 기간 선택(period_input)으로 진행."""
    account_ids = value.get("account_ids") or []
    if value.get("account_selection_outcome") != "selected" or not account_ids:
        await _external_cancel(redis_stream, chat_session_id, "조회를 취소했어요.")
        return
    state = _WF_STATE.setdefault(str(chat_session_id), {})
    state["account_ids"] = [str(a) for a in account_ids]
    await _emit_need_input(
        redis_stream,
        chat_session_id,
        execution_context_id,
        UI_PERIOD_SELECTION,
        "period_input",
        "조회 기간을 선택해 주세요.",
        build_period_input_view(),
    )


async def _run_query_after_period(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
    execution_context_id: UUID | None,
) -> None:
    """기간 확정 → 거래내역이면 결과, 합계면 유형 선택으로 분기(활성 wf 기준)."""
    if value.get("period_selection_outcome") != "selected":
        await _external_cancel(redis_stream, chat_session_id, "조회를 취소했어요.")
        return
    state = _WF_STATE.setdefault(str(chat_session_id), {})
    state["start_date"] = value.get("start_date")
    state["end_date"] = value.get("end_date")

    if state.get("wf") == "summary":
        await _emit_need_input(
            redis_stream,
            chat_session_id,
            execution_context_id,
            UI_SUMMARY_TYPE_SELECTION,
            "option_select",
            "합계 유형을 선택해 주세요.",
            build_summary_type_view(),
        )
        return

    # 거래내역 결과.
    payload = build_transaction_list(
        state.get("account_ids", []),
        state.get("start_date"),
        state.get("end_date"),
        f"txq_{uuid4().hex[:12]}",
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "거래내역을 불러오고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.COMPONENT,
        "거래내역을 불러왔어요.",
        metadata={"component": "transaction_list", "params": payload},
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        "다른 도움이 필요하시면 말씀해 주세요.",
    )
    _WF_STATE.pop(str(chat_session_id), None)


async def _run_summary_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
) -> None:
    """합계 유형 확정 → amount_summary 결과 발행(계약 4.4)."""
    if value.get("option_selection_outcome") != "selected":
        await _external_cancel(redis_stream, chat_session_id, "조회를 취소했어요.")
        return
    state = _WF_STATE.setdefault(str(chat_session_id), {})
    summary_type = value.get("option") or "spending"
    payload = build_amount_summary(
        state.get("account_ids", []),
        state.get("start_date"),
        state.get("end_date"),
        str(summary_type),
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "합계를 계산하고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.COMPONENT,
        "합계를 불러왔어요.",
        metadata={"component": "amount_summary", "params": payload},
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        "다른 도움이 필요하시면 말씀해 주세요.",
    )
    _WF_STATE.pop(str(chat_session_id), None)


async def _run_balance_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
) -> None:
    """선택된 계좌의 잔액 결과(balance_result)를 발행한다(계약 4.2)."""
    if value.get("account_selection_outcome") != "selected":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "잔액 조회를 취소했어요.",
            delay=False,
        )
        return

    account_ids = value.get("account_ids") or []
    payload = build_balance_result([str(account_id) for account_id in account_ids])
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "잔액을 조회하고 있어요...",
        delay=False,
    )
    # 결과 UI 는 inline payload(ADR C3): component 이벤트 params 에 표시 데이터를 싣고
    # FE 가 fetch 없이 즉시 렌더한다(마스킹된 소용량 카드라 SSE 전송에 문제 없음).
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.COMPONENT,
        "잔액을 불러왔어요.",
        metadata={"component": "balance_result", "params": payload},
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        "다른 도움이 필요하시면 말씀해 주세요.",
    )


async def run_after_approval(
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
    component: str | None = None,
    user_id: UUID | None = None,
) -> None:
    """confirm 카드 승인/거절 이후의 후속 턴을 발행한다.

    `component` 로 어떤 confirm(transfer/autotransfer)인지 구분한다(FE 가 전달).
    `user_id` 가 있으면 송금 승인 시 계정계 실이체를 시도한다(Phase 2).
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        if component == "external_transfer":
            await _run_external_after_approval(
                redis_stream, chat_session_id, approval_id, decision
            )
        elif component in _SETTING_COMPONENTS:
            await _run_setting_result(
                redis_stream, chat_session_id, approval_id, decision
            )
        elif component == "autotransfer":
            await _run_autotransfer_result(
                redis_stream, chat_session_id, approval_id, decision, args
            )
        else:
            await _run_transfer_result(
                redis_stream, chat_session_id, approval_id, decision, args, user_id
            )
    finally:
        await redis_stream.aclose()


async def _run_setting_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    confirmation_id: str,
    decision: str,
) -> None:
    """설정(별칭) confirm_modal 결과 후속 턴(계약 4.6).

    승인 상태는 chat_service 가 이미 실제 Confirmation 에 반영했다. 여기서는 결과 UI
    또는 재요청/취소만 발행한다. 결과 데이터는 Confirmation.fixed_data 에서 복원한다.
    """
    if decision == "cancelled":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "별칭 변경을 취소했어요.",
            delay=False,
        )
        return

    fixed_data, execution_context_id = await _load_confirmation(confirmation_id)

    if decision == "change_requested":
        # 수정: 기존 Confirmation 은 폐기됐고, 별칭을 다시 입력받는다(re-prepare).
        await _run_alias_input(
            redis_stream, chat_session_id, execution_context_id, None
        )
        return

    alias = (fixed_data or {}).get("alias")
    completed_at = datetime.now(timezone.utc).isoformat()
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "별칭을 변경하고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.COMPONENT,
        "별칭을 변경했어요.",
        metadata={
            "component": "setting_result",
            "params": build_alias_setting_result(alias, completed_at),
        },
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        "다른 도움이 필요하시면 말씀해 주세요.",
    )


async def _run_transfer_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
    user_id: UUID | None = None,
) -> None:
    if decision != "approve":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "송금을 취소했어요.",
            delay=False,
        )
        return

    amount = (args or {}).get("amount", _SAMPLE_ARGS["amount"])
    name = (args or {}).get("name", _SAMPLE_ARGS["name"])
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "송금을 처리하고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.TOOL_CALL,
        "송금을 실행하고 있어요...",
        metadata={"tool": "transfer", "approval_id": approval_id},
    )
    # 실이체는 수행하지 않는다(D5: env-고정 수취처 데모 로직 제거). 실제 송금은
    # Stage 7 의 실 Agent 연동이 agent-tools Prepare→승인→인증→Execute 로 수행한다.
    _ = user_id
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        f"{name}님께 {int(amount):,}원을 보냈어요. ✓",
    )


async def _run_autotransfer_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
) -> None:
    if decision != "approve":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "자동이체 등록을 취소했어요.",
            delay=False,
        )
        return

    amount = (args or {}).get("amount", _AUTOTRANSFER_SAMPLE_ARGS["amount"])
    day = (args or {}).get("day", _AUTOTRANSFER_SAMPLE_ARGS["day"])
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "자동이체를 등록하고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.TOOL_CALL,
        "자동이체를 등록하고 있어요...",
        metadata={"tool": "autotransfer", "approval_id": approval_id},
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        f"{day} {int(amount):,}원 자동이체를 등록했어요. ✓",
    )
