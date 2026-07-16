"""Exercise the deployed Backend product chat path through Nginx."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from typing import Any
from uuid import uuid4


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str | None = None,
    timeout: float = 15,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    if not isinstance(body, dict) or body.get("success") is not True:
        raise RuntimeError(f"Unexpected response from {url}")
    return body


def run_smoke(base_url: str) -> None:
    api = f"{base_url.rstrip('/')}/backendApi/api/v1"
    email = f"ci-smoke-{uuid4().hex}@example.com"
    password = f"Ci-smoke-{uuid4().hex}"

    _request_json(
        f"{api}/users/signup",
        method="POST",
        payload={"email": email, "password": password, "name": "CI smoke"},
    )
    login = _request_json(
        f"{api}/users/login",
        method="POST",
        payload={"email": email, "password": password},
    )
    login_data = login.get("data")
    if not isinstance(login_data, dict) or not isinstance(
        login_data.get("access_token"), str
    ):
        raise RuntimeError("Login response did not contain an access token")
    token = login_data["access_token"]

    ticket = _request_json(f"{api}/sse/ticket", token=token)
    ticket_data = ticket.get("data")
    if not isinstance(ticket_data, dict):
        raise RuntimeError("SSE ticket response did not contain data")
    chat_session_id = ticket_data.get("chat_session_id")
    sse_session_id = ticket_data.get("sse_session_id")
    if not isinstance(chat_session_id, str) or not isinstance(sse_session_id, str):
        raise RuntimeError("SSE ticket response was incomplete")

    chat = _request_json(
        f"{api}/chat",
        method="POST",
        token=token,
        payload={"chat_session_id": chat_session_id, "message": "내 잔액 알려줘"},
    )
    chat_data = chat.get("data")
    if (
        not isinstance(chat_data, dict)
        or chat_data.get("chat_session_id") != chat_session_id
    ):
        raise RuntimeError("Product chat did not accept the bound session")

    query = urllib.parse.urlencode({"sse_session_id": sse_session_id})
    with urllib.request.urlopen(f"{api}/sse/connect?{query}", timeout=15) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" not in content_type:
            raise RuntimeError("SSE endpoint did not return an event stream")
        stream = response.read().decode()
    if "[DONE]" not in stream:
        raise RuntimeError("Product chat SSE stream did not complete")

    print("Backend product signup/login/chat/SSE smoke passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    run_smoke(args.base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
