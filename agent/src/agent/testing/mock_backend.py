"""실제 Backend 없이 Agent HTTP 계약을 검증하는 Mock Transport."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class MockExchange:
    """Mock Backend가 실제로 처리한 요청과 응답 한 쌍."""

    request: httpx.Request
    status_code: int
    response_payload: Mapping[str, Any]


class MockBackend:
    """HTTP Method와 Path별 응답 Queue와 수신 요청을 관리한다."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.exchanges: list[MockExchange] = []
        self._responses: dict[
            tuple[str, str],
            deque[tuple[int, Mapping[str, Any]]],
        ] = defaultdict(deque)

    def add_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any],
        *,
        status_code: int = 200,
    ) -> None:
        """지정 Method와 Path가 호출될 때 반환할 JSON을 Queue에 추가한다."""

        self._responses[(method.upper(), path)].append((status_code, payload))

    def add_success(
        self,
        method: str,
        path: str,
        data: Mapping[str, Any],
        *,
        message: str = "처리 완료",
    ) -> None:
        """Agent Tool과 Webhook 공통 성공 Envelope를 추가한다."""

        self.add_json(
            method,
            path,
            {"success": True, "message": message, "data": data},
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        """httpx.MockTransport가 호출하는 동기 응답 Handler."""

        self.requests.append(request)
        key = (request.method.upper(), request.url.path)
        responses = self._responses.get(key)
        if not responses:
            raise AssertionError(f"등록되지 않은 Mock Backend 요청입니다: {key}")
        status_code, payload = responses.popleft()
        self.exchanges.append(
            MockExchange(
                request=request,
                status_code=status_code,
                response_payload=payload,
            )
        )
        return httpx.Response(status_code, json=dict(payload))

    def requests_to(self, method: str, path: str) -> list[httpx.Request]:
        """특정 계약 Endpoint로 전송된 요청만 반환한다."""

        return [
            request
            for request in self.requests
            if request.method == method.upper() and request.url.path == path
        ]

    def assert_all_responses_used(self) -> None:
        """Scenario에 등록했지만 사용되지 않은 Mock 응답이 없음을 확인한다."""

        unused = {
            f"{method} {path}": len(responses)
            for (method, path), responses in self._responses.items()
            if responses
        }
        if unused:
            raise AssertionError(f"사용되지 않은 Mock Backend 응답입니다: {unused}")

    def exchange_timeline(
        self,
        *,
        include_payload: bool = False,
    ) -> list[dict[str, Any]]:
        """Step 학습용으로 실제 Mock 요청과 응답을 순서대로 반환한다."""

        return [
            _exchange_summary(exchange, include_payload=include_payload)
            for exchange in self.exchanges
        ]


def _exchange_summary(
    exchange: MockExchange,
    *,
    include_payload: bool,
) -> dict[str, Any]:
    request = exchange.request
    summary: dict[str, Any] = {
        "method": request.method,
        "path": request.url.path,
        "status_code": exchange.status_code,
    }
    if not include_payload:
        return summary

    if request.method == "GET":
        summary["request"] = dict(request.url.params.multi_items())
    elif request.content:
        try:
            summary["request"] = json.loads(request.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            summary["request"] = "JSON이 아닌 요청"
    summary["response"] = dict(exchange.response_payload)
    return summary
