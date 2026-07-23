"""Compatibility checks for the Agent team's public HTTP models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.schemas import ChatRequest, ChatResponse
from security.redteam.models import AgentResponse


def test_public_chat_request_fields_and_bounds():
    request = ChatRequest(message="hello", user_id="user_001", thread_id=None)

    assert request.model_dump() == {
        "message": "hello",
        "thread_id": None,
        "user_id": "user_001",
    }
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 2001, user_id="user_001", thread_id=None)


@pytest.mark.parametrize(
    "status",
    ["completed", "waiting_input", "blocked", "no_match", "failed"],
)
def test_public_statuses_are_consumable(status):
    response = ChatResponse.model_validate(
        {
            "reply": "result",
            "status": status,
            "thread_id": "thread",
            "prompt_for": None,
            "ui": None,
        }
    )

    consumed = AgentResponse.model_validate(response.model_dump(mode="json"))

    assert consumed.status == status


@pytest.mark.parametrize(
    "ui",
    [
        {"type": "account_card_list", "options": [], "multi": False},
        {"type": "search_select", "options": []},
        {"type": "number_input"},
        {"type": "confirm_modal", "display": {}, "actions": []},
        {"type": "auth_request", "methods": [], "actions": []},
    ],
)
def test_public_ui_variants_are_consumable(ui):
    response = ChatResponse.model_validate(
        {
            "reply": "select",
            "status": "waiting_input",
            "thread_id": "thread",
            "prompt_for": "opaque.state",
            "ui": ui,
        }
    )

    consumed = AgentResponse.model_validate(response.model_dump(mode="json"))

    assert consumed.ui is not None
    assert consumed.ui.type == ui["type"]
