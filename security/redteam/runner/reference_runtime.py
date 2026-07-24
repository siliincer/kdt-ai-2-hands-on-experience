"""Translate an injected Agent workflow testbed run into bounded QA evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from datetime import date
from typing import Any, Protocol

from security.redteam.models import (
    AgentResponse,
    AgentUiEnvelope,
    BusinessWorkflow,
    WorkflowExecutionEvidence,
    WorkflowToolRequestEvidence,
    WorkflowTraceEvidence,
    WorkflowWebhookEvidence,
)
from security.redteam.runner.sanitizer import contains_sensitive_data

MAX_REFERENCE_TIMELINE_ITEMS = 100
MAX_REFERENCE_WEBHOOK_EVENTS = 100
MAX_REFERENCE_TRACE_ITEMS = 200
MAX_REFERENCE_PROJECTION_BYTES = 1_048_576
MAX_REFERENCE_STRUCTURE_NODES = 10_000
MAX_REFERENCE_STRUCTURE_DEPTH = 20
MAX_REFERENCE_STRING_BYTES = 1_048_576
_STATE_ISOLATION_KEYS = {
    "account_results",
    "account_id",
    "account_ids",
    "auth_context_id",
    "balance_results",
    "confirmation_id",
    "from_account_id",
    "summary_result",
    "recipient_id",
    "recipient_ids",
    "selection_id",
    "to_account_id",
    "transaction_query_id",
}


class ReferenceRunResult(Protocol):
    @property
    def agent_thread_id(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def pending_interaction(self) -> Mapping[str, Any] | None: ...


class ReferenceWorkflowTestbed(Protocol):
    async def start(
        self,
        *,
        message: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        initial_state: Mapping[str, Any] | None = None,
    ) -> ReferenceRunResult: ...

    async def state(self, agent_thread_id: str) -> dict[str, Any]: ...

    async def resume_input(
        self,
        *,
        agent_thread_id: str,
        request_id: str,
        chat_session_id: str,
        execution_context_id: str,
        input_request_id: str,
        value: Mapping[str, Any],
    ) -> ReferenceRunResult: ...

    async def resume(
        self,
        agent_thread_id: str,
        request: Any,
    ) -> ReferenceRunResult: ...

    def request_timeline(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]: ...

    def webhook_events(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]: ...


async def execute_reference_start(
    testbed: ReferenceWorkflowTestbed,
    *,
    message: str,
    request_id: str,
    chat_session_id: str,
    execution_context_id: str,
    workflow_contract: Mapping[str, Any] | None = None,
) -> AgentResponse:
    """Run one reference workflow and preserve state-backed execution evidence."""

    result = await testbed.start(
        message=message,
        request_id=request_id,
        chat_session_id=chat_session_id,
        execution_context_id=execution_context_id,
    )
    return await _response_from_testbed(testbed, result, workflow_contract)


async def execute_reference_input_resume(
    testbed: ReferenceWorkflowTestbed,
    *,
    agent_thread_id: str,
    request_id: str,
    chat_session_id: str,
    execution_context_id: str,
    input_request_id: str,
    value: Mapping[str, Any],
    workflow_contract: Mapping[str, Any] | None = None,
) -> AgentResponse:
    """Resume one validated read-workflow input and capture cumulative evidence."""

    result = await testbed.resume_input(
        agent_thread_id=agent_thread_id,
        request_id=request_id,
        chat_session_id=chat_session_id,
        execution_context_id=execution_context_id,
        input_request_id=input_request_id,
        value=value,
    )
    if result.agent_thread_id != agent_thread_id:
        raise ValueError("reference resume changed agent thread")
    return await _response_from_testbed(testbed, result, workflow_contract)


async def execute_reference_resume(
    testbed: ReferenceWorkflowTestbed,
    *,
    agent_thread_id: str,
    resume_request: Any,
    workflow_contract: Mapping[str, Any] | None = None,
) -> AgentResponse:
    """Resume with a runtime-validated request without importing Agent models."""

    result = await testbed.resume(agent_thread_id, resume_request)
    if result.agent_thread_id != agent_thread_id:
        raise ValueError("reference resume changed agent thread")
    return await _response_from_testbed(testbed, result, workflow_contract)


async def _response_from_testbed(
    testbed: ReferenceWorkflowTestbed,
    result: ReferenceRunResult,
    workflow_contract: Mapping[str, Any] | None,
) -> AgentResponse:
    state = await testbed.state(result.agent_thread_id)
    _validate_structure(state, "reference state")
    runtime_status = _bounded_text(result.status, "runtime status", required=True)
    state_status = _bounded_text(state.get("status"), "state status", required=True)
    raw_workflow_id = state.get("workflow_id")
    if raw_workflow_id is None and state_status in {"blocked", "no_match"}:
        raw_workflow_id = BusinessWorkflow.GLOBAL_AGENT_ENTRY
    observed_workflow = BusinessWorkflow(raw_workflow_id)
    timeline = _bounded_records(
        testbed.request_timeline(include_payload=True),
        "reference timeline",
        MAX_REFERENCE_TIMELINE_ITEMS,
    )
    webhook_events = _bounded_records(
        testbed.webhook_events(),
        "reference webhook events",
        MAX_REFERENCE_WEBHOOK_EVENTS,
    )
    webhook_payload_events = _bounded_records(
        testbed.webhook_events(include_payload=True),
        "reference webhook payload events",
        MAX_REFERENCE_WEBHOOK_EVENTS,
    )
    backend_exchanges = _backend_exchanges(testbed)
    _validate_structure(timeline, "reference timeline")
    _validate_structure(webhook_payload_events, "reference webhook payloads")
    if backend_exchanges is not None:
        _validate_structure(backend_exchanges, "reference backend exchanges")
    digest_key = _digest_key(testbed)
    (
        request_ids,
        execution_context_ids,
        chat_session_ids,
        tool_request_paths,
        tool_requests,
        contract_tool_ids,
    ) = _collect_timeline_evidence(
        timeline,
        workflow_contract,
        digest_key,
    )
    for chat_session_id in _webhook_chat_session_ids(webhook_payload_events):
        if chat_session_id not in chat_session_ids:
            chat_session_ids.append(chat_session_id)
    evidence = WorkflowExecutionEvidence(
        observed_workflow_id=observed_workflow,
        runtime_status=runtime_status,
        state_status=state_status,
        request_ids=request_ids,
        execution_context_ids=execution_context_ids,
        chat_session_ids=chat_session_ids,
        tool_request_paths=tool_request_paths,
        tool_requests=tool_requests,
        contract_tool_ids=contract_tool_ids,
        webhooks=_webhook_evidence(webhook_events),
        pending_identifiers=_pending_identifiers(result.pending_interaction),
        trace=_trace_evidence(state.get("execution_trace")),
        state_contains_sensitive_data=contains_sensitive_data(
            state,
            _redact_fields(testbed),
        ),
        webhook_payloads_contain_sensitive_data=contains_sensitive_data(
            webhook_payload_events,
            _redact_fields(testbed),
        ),
        tool_arguments_valid=_tool_arguments_valid(
            timeline,
            backend_exchanges,
            _expected_tool_requests(workflow_contract),
            require_complete=result.status != "waiting",
        ),
        backend_exchanges_valid=(
            _backend_exchanges_valid(backend_exchanges) if backend_exchanges is not None else None
        ),
        state_projection_digest=_digest(state, digest_key),
        state_projection_values=_state_projection_values(state, digest_key),
        webhook_payload_digest=_digest(webhook_payload_events, digest_key),
        backend_exchange_digest=(_digest(backend_exchanges, digest_key) if backend_exchanges is not None else None),
    )
    return AgentResponse(
        reply=_bounded_text(state.get("final_response"), "final response"),
        status=_public_status(runtime_status, state_status),
        thread_id=result.agent_thread_id,
        prompt_for=_optional_bounded_text(state.get("prompt_for"), "prompt_for"),
        ui=_latest_ui(webhook_payload_events),
        execution_evidence=evidence,
    )


def _collect_timeline_evidence(
    timeline: list[dict[str, Any]],
    contract: Mapping[str, Any] | None,
    digest_key: bytes,
) -> tuple[
    list[str],
    list[str],
    list[str],
    list[str],
    list[WorkflowToolRequestEvidence],
    list[str],
]:
    transport_tools, webhook_step_tools = _contract_tool_maps(contract)
    identity_keys = ("request_id", "execution_context_id", "chat_session_id")
    identity_values = {key: [] for key in identity_keys}
    identity_seen = {key: set() for key in identity_keys}
    paths = []
    requests = []
    tool_ids = []
    for item in timeline:
        for key in identity_keys:
            value = item.get(key)
            if value is None:
                continue
            text = _bounded_text(value, f"timeline {key}", required=True)
            if text not in identity_seen[key]:
                identity_seen[key].add(text)
                identity_values[key].append(text)
        method = item.get("method")
        path = item.get("path")
        step_id = item.get("step_id")
        if not isinstance(method, str) or not isinstance(path, str):
            raise ValueError("reference tool request requires method and path")
        if path == "/api/v1/webhooks/agent":
            if isinstance(step_id, str) and step_id in webhook_step_tools:
                tool_ids.append(webhook_step_tools[step_id])
            continue
        query_keys = item.get("query_keys", [])
        if not isinstance(query_keys, list) or any(not isinstance(key, str) for key in query_keys):
            raise ValueError("reference tool request query keys must be text")
        paths.append(path)
        requests.append(
            WorkflowToolRequestEvidence(
                method=method,
                path=path,
                query_keys=query_keys,
                payload_digest=(
                    _digest(item["payload"], digest_key) if isinstance(item.get("payload"), Mapping) else None
                ),
            )
        )
        tool_id = transport_tools.get((method, path))
        if tool_id is not None:
            tool_ids.append(tool_id)
    return (
        identity_values["request_id"],
        identity_values["execution_context_id"],
        identity_values["chat_session_id"],
        paths,
        requests,
        tool_ids,
    )


def _contract_tool_maps(
    contract: Mapping[str, Any] | None,
) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    if contract is None:
        return {}, {}
    steps = contract.get("steps")
    if not isinstance(steps, list):
        raise ValueError("reference workflow contract steps must be a list")
    transport_tools = {}
    webhook_step_tools = {}
    for step in steps:
        if not isinstance(step, Mapping):
            raise ValueError("reference workflow contract steps must be objects")
        step_id = step.get("step_id")
        tool_id = step.get("tool_id")
        action = step.get("external_action")
        if not isinstance(step_id, str) or not isinstance(tool_id, str) or not tool_id:
            continue
        if isinstance(action, str):
            method, separator, path = action.partition(" ")
            if separator and method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                transport_tools[(method, path)] = tool_id
        if step.get("interaction_mode") in {"webhook", "webhook_then_resume"}:
            webhook_step_tools[step_id] = tool_id
    return transport_tools, webhook_step_tools


def _bounded_records(value: object, name: str, maximum: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds {maximum} entries")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{name} entries must be objects")
    return value


def _redact_fields(testbed: ReferenceWorkflowTestbed) -> set[str]:
    value = getattr(testbed, "_redteam_redact_fields", frozenset())
    return set(value) if isinstance(value, (set, frozenset)) else set()


def _backend_exchanges(
    testbed: ReferenceWorkflowTestbed,
) -> list[dict[str, Any]] | None:
    backend = getattr(testbed, "_redteam_backend", None)
    exchange_timeline = getattr(backend, "exchange_timeline", None)
    if not callable(exchange_timeline):
        return None
    return _bounded_records(
        exchange_timeline(include_payload=True),
        "reference backend exchanges",
        MAX_REFERENCE_TIMELINE_ITEMS,
    )


def _digest_key(testbed: ReferenceWorkflowTestbed) -> bytes:
    value = getattr(testbed, "_redteam_digest_key", None)
    if isinstance(value, bytes) and len(value) >= 32:
        return value
    value = secrets.token_bytes(32)
    try:
        setattr(testbed, "_redteam_digest_key", value)
    except (AttributeError, TypeError):
        pass
    return value


def _validate_structure(value: object, name: str) -> None:
    stack = [(value, 0)]
    nodes = 0
    string_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_REFERENCE_STRUCTURE_NODES:
            raise ValueError(f"{name} contains too many values")
        if depth > MAX_REFERENCE_STRUCTURE_DEPTH:
            raise ValueError(f"{name} nesting is too deep")
        if isinstance(item, str):
            string_bytes += len(item.encode("utf-8"))
            if string_bytes > MAX_REFERENCE_STRING_BYTES:
                raise ValueError(f"{name} string content is too large")
        elif isinstance(item, Mapping):
            stack.extend((key, depth + 1) for key in item)
            stack.extend((nested, depth + 1) for nested in item.values())
        elif isinstance(item, list):
            stack.extend((nested, depth + 1) for nested in item)


def _digest(value: object, key: bytes) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    if len(encoded) > MAX_REFERENCE_PROJECTION_BYTES:
        raise ValueError("reference evidence projection exceeds byte limit")
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def _state_projection_values(state: Mapping[str, Any], digest_key: bytes) -> dict[str, list[str]]:
    projected: dict[str, set[str]] = {}

    def visit(value: object, active_key: str | None = None) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized = key.casefold() if isinstance(key, str) else ""
                selected = normalized if normalized in _STATE_ISOLATION_KEYS else None
                if selected is not None and isinstance(nested, (Mapping, list)):
                    projected.setdefault(selected, set()).add(_digest(nested, digest_key))
                else:
                    visit(nested, selected)
            return
        if isinstance(value, list):
            for nested in value:
                visit(nested, active_key)
            return
        if active_key is not None and value is not None:
            projected.setdefault(active_key, set()).add(_digest(value, digest_key))

    visit(state)
    if len(projected) > 100 or any(len(values) > 100 for values in projected.values()):
        raise ValueError("reference state projection exceeds value limit")
    return {key: sorted(values) for key, values in sorted(projected.items())}


def _backend_exchanges_valid(exchanges: list[dict[str, Any]]) -> bool:
    return bool(exchanges) and all(
        isinstance(exchange.get("status_code"), int)
        and 200 <= exchange["status_code"] < 300
        and isinstance(exchange.get("response"), Mapping)
        for exchange in exchanges
    )


def _tool_arguments_valid(
    timeline: list[dict[str, Any]],
    exchanges: list[dict[str, Any]] | None,
    expected_requests: list[dict[str, Any]],
    *,
    require_complete: bool = True,
) -> bool | None:
    def collect(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "method": item.get("method"),
                "path": str(item.get("path", "")),
                "payload": item.get("request", item.get("payload")),
            }
            for item in source
            if str(item.get("path", "")).startswith("/api/v1/agent-tools/")
        ]

    timeline_requests = collect(timeline)
    exchange_requests = collect(exchanges) if exchanges is not None else None
    requests = exchange_requests if exchange_requests is not None else timeline_requests
    if not requests:
        return None
    if (
        len(requests) > len(expected_requests)
        or (require_complete and len(requests) != len(expected_requests))
        or (
            exchange_requests is not None
            and [(item["method"], item["path"]) for item in exchange_requests]
            != [(item["method"], item["path"]) for item in timeline_requests]
        )
    ):
        return False
    known_accounts = _known_account_ids(exchanges or [])
    for request, expected in zip(requests, expected_requests):
        payload = request["payload"]
        required_arguments = expected["required_arguments"]
        optional_arguments = expected.get("optional_arguments", {})
        if (
            request["method"] != expected["method"]
            or request["path"] != expected["path"]
            or not isinstance(payload, Mapping)
            or not set(required_arguments) <= set(payload)
            or not isinstance(optional_arguments, Mapping)
            or not set(payload) <= set(required_arguments) | set(optional_arguments)
            or not _valid_business_arguments(payload, known_accounts)
            or any(not _argument_value_matches(payload.get(key), value) for key, value in required_arguments.items())
            or any(
                key in payload and not _optional_argument_matches(payload[key], expectation)
                for key, expectation in optional_arguments.items()
            )
        ):
            return False
    return True


def _argument_value_matches(actual: object, expected: object) -> bool:
    if isinstance(expected, bool) and isinstance(actual, str):
        return actual.casefold() == str(expected).casefold()
    if isinstance(expected, int) and not isinstance(expected, bool):
        return actual == expected or (isinstance(actual, str) and actual.isdecimal() and int(actual) == expected)
    if isinstance(expected, list) and len(expected) == 1 and isinstance(actual, str):
        return actual == expected[0]
    return actual == expected


def _optional_argument_matches(actual: object, expectation: object) -> bool:
    if not isinstance(actual, str) or not isinstance(expectation, Mapping):
        return False
    allowed_values = expectation.get("allowed_values")
    return isinstance(allowed_values, (list, set, tuple)) and actual.strip() in {
        value.strip() for value in allowed_values if isinstance(value, str)
    }


def _expected_tool_requests(
    contract: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if contract is None:
        return []
    raw = contract.get("_reference_expected_tool_requests", [])
    if not isinstance(raw, list):
        raise ValueError("reference tool request expectations are invalid")
    expected = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("reference tool request expectations are invalid")
        method = item.get("method")
        path = item.get("path")
        arguments = item.get("required_arguments")
        optional_arguments = item.get("optional_arguments", {})
        if (
            not isinstance(method, str)
            or not isinstance(path, str)
            or not isinstance(arguments, Mapping)
            or not isinstance(optional_arguments, Mapping)
            or any(
                not isinstance(key, str) or not isinstance(value, Mapping) for key, value in optional_arguments.items()
            )
        ):
            raise ValueError("reference tool request expectations are invalid")
        expected.append(
            {
                "method": method,
                "path": path,
                "required_arguments": dict(arguments),
                "optional_arguments": {key: dict(value) for key, value in optional_arguments.items()},
            }
        )
    return expected


def _known_account_ids(exchanges: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for exchange in exchanges:
        if exchange.get("path") != "/api/v1/agent-tools/accounts":
            continue
        status_code = exchange.get("status_code")
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            continue
        response = exchange.get("response")
        if not isinstance(response, Mapping):
            continue
        _collect_values(response, {"account_id", "account_ids"}, values)
    return values


def _collect_values(value: object, keys: set[str], target: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in keys:
                if isinstance(nested, str):
                    target.add(nested)
                elif isinstance(nested, list):
                    target.update(item for item in nested if isinstance(item, str))
            _collect_values(nested, keys, target)
    elif isinstance(value, list):
        for nested in value:
            _collect_values(nested, keys, target)


def _valid_business_arguments(
    value: object,
    known_accounts: set[str],
) -> bool:
    if not isinstance(value, Mapping):
        return True
    for key, nested in value.items():
        if key.endswith("_hint") and (not isinstance(nested, str) or not 0 < len(nested.strip()) <= 200):
            return False
        if key in {"account_id", "from_account_id", "to_account_id"}:
            if not isinstance(nested, str) or not nested:
                return False
            if known_accounts and nested not in known_accounts:
                return False
        if key == "exclude_account_ids" and isinstance(nested, str):
            nested = [nested]
        if key in {"account_ids", "exclude_account_ids"}:
            if not isinstance(nested, list) or any(not isinstance(item, str) or not item for item in nested):
                return False
            if len(nested) != len(set(nested)):
                return False
            if known_accounts and not set(nested) <= known_accounts:
                return False
        if key in {"page_size", "limit"}:
            numeric = int(nested) if isinstance(nested, str) and nested.isdecimal() else nested
            if not isinstance(numeric, int) or isinstance(numeric, bool) or not 1 <= numeric <= 100:
                return False
        if key == "amount" and (
            not isinstance(nested, int) or isinstance(nested, bool) or not 1 <= nested <= 1_000_000_000
        ):
            return False
        if key.endswith("_date"):
            if not isinstance(nested, str):
                return False
            try:
                parsed = date.fromisoformat(nested)
            except ValueError:
                return False
            if not 2000 <= parsed.year <= 2100:
                return False
        if key == "summary_type" and nested not in {"spending", "income"}:
            return False
        if (
            key == "transaction_type"
            and nested is not None
            and nested
            not in {
                "deposit",
                "withdrawal",
                "transfer",
                "card_payment",
                "atm_withdrawal",
                "fee",
                "interest",
            }
        ):
            return False
        if (
            key == "account_capability"
            and nested is not None
            and nested
            not in {
                "inquiry",
                "withdraw",
                "deposit",
                "settings",
            }
        ):
            return False
        if key in {"alias", "account_hint", "recipient_name_hint", "keyword"}:
            if nested is not None and (not isinstance(nested, str) or not nested.strip() or len(nested) > 100):
                return False
        if isinstance(nested, (Mapping, list)) and not _valid_nested_arguments(
            nested,
            known_accounts,
        ):
            return False
    start = value.get("start_date")
    end = value.get("end_date")
    if isinstance(start, str) and isinstance(end, str):
        if date.fromisoformat(end) < date.fromisoformat(start):
            return False
    from_account = value.get("from_account_id")
    to_account = value.get("to_account_id")
    if isinstance(from_account, str) and from_account == to_account:
        return False
    return True


def _valid_nested_arguments(
    value: object,
    known_accounts: set[str],
) -> bool:
    if isinstance(value, Mapping):
        return _valid_business_arguments(value, known_accounts)
    if isinstance(value, list):
        return all(_valid_nested_arguments(item, known_accounts) for item in value)
    return True


def _webhook_chat_session_ids(events: list[dict[str, Any]]) -> list[str]:
    values = []
    seen = set()
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        value = payload.get("chat_session_id")
        if value is None:
            continue
        text = _bounded_text(value, "webhook chat_session_id", required=True)
        if text not in seen:
            seen.add(text)
            values.append(text)
    return values


def _webhook_evidence(events: list[dict[str, Any]]) -> list[WorkflowWebhookEvidence]:
    evidence = []
    for event in events:
        event_type = _bounded_text(
            event.get("event_type"),
            "webhook event",
            required=True,
        )
        step_id = _optional_bounded_text(event.get("step_id"), "webhook step_id")
        evidence.append(WorkflowWebhookEvidence(event_type=event_type, step_id=step_id))
    return evidence


def _pending_identifiers(pending: Mapping[str, Any] | None) -> dict[str, str]:
    if pending is None:
        return {}
    identifiers = {}
    for key, value in pending.items():
        if not isinstance(key, str) or not key.endswith("_id") or value is None:
            continue
        identifiers[key] = _bounded_text(value, f"pending {key}", required=True)
    return identifiers


def _trace_evidence(value: object) -> list[WorkflowTraceEvidence]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("reference execution trace must be a list")
    if len(value) > MAX_REFERENCE_TRACE_ITEMS:
        raise ValueError(f"reference execution trace exceeds {MAX_REFERENCE_TRACE_ITEMS} entries")
    trace = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("reference execution trace entries must be objects")
        trace.append(
            WorkflowTraceEvidence(
                step_id=_bounded_text(item.get("step"), "trace step", required=True),
                route_key=_optional_bounded_text(item.get("route_key"), "route key"),
            )
        )
    return trace


def _latest_ui(events: list[dict[str, Any]]) -> AgentUiEnvelope | None:
    for event in reversed(events):
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping) and isinstance(metadata.get("ui"), Mapping):
            return AgentUiEnvelope.model_validate(dict(metadata["ui"]))
    return None


def _public_status(runtime_status: str, state_status: str) -> str:
    if runtime_status == "waiting":
        return "waiting_input"
    if runtime_status == "failed" or state_status == "workflow_failed":
        return "failed"
    if state_status in {"blocked", "no_match"}:
        return state_status
    return "completed"


def _optional_bounded_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, field, required=True)


def _bounded_text(value: object, field: str, *, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value) or len(value) > 20_000:
        raise ValueError(f"reference {field} must be bounded text")
    return value
