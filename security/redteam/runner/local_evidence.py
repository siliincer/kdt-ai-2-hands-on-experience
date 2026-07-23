"""Pure projection of local Agent graph state into bounded QA evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from security.redteam.models import BusinessWorkflow

_WORKFLOW_IDS = {workflow.value for workflow in BusinessWorkflow}
_GLOBAL_TERMINAL_STEPS = {
    "blocked": {"emit_global_blocked", "show_global_blocked"},
    "no_match": {"emit_no_matching_workflow", "show_no_matching_workflow"},
}


def workflow_evidence(
    state: object,
    public_status: str,
) -> dict[str, Any] | None:
    if not isinstance(state, Mapping):
        return None
    workflow_id = state.get("workflow_id")
    if workflow_id not in _WORKFLOW_IDS:
        return None
    raw_trace = state.get("execution_trace")
    bounded_trace = raw_trace[:200] if isinstance(raw_trace, list) else []
    trace = []
    for item in bounded_trace:
        if not isinstance(item, Mapping):
            continue
        step_id = item.get("step")
        route_key = item.get("route_key")
        if not isinstance(step_id, str) or not 1 <= len(step_id) <= 200:
            continue
        if not isinstance(route_key, str) or not route_key or len(route_key) > 200:
            route_key = None
        trace.append({"step_id": step_id, "route_key": route_key})
    state_status = state.get("status")
    if workflow_id == BusinessWorkflow.GLOBAL_AGENT_ENTRY and not trace:
        terminal_step = state.get("current_step_id")
        allowed_steps = (
            _GLOBAL_TERMINAL_STEPS.get(state_status, set())
            if isinstance(state_status, str)
            else set()
        )
        if isinstance(terminal_step, str) and terminal_step in allowed_steps:
            route_key = state.get("route_key")
            if not isinstance(route_key, str) or not 1 <= len(route_key) <= 200:
                route_key = None
            trace.append({"step_id": terminal_step, "route_key": route_key})
    return {
        "observed_workflow_id": workflow_id,
        "runtime_status": public_status,
        "state_status": (
            state_status
            if isinstance(state_status, str) and 1 <= len(state_status) <= 100
            else public_status
        ),
        "trace": trace,
    }
