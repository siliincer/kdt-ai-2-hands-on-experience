"""E2E 공용 fixture.

mock 없음 — 실제로 떠 있는 backend(+postgres) / frontend(vite dev) 를 그대로 씀.
사전 준비는 e2e/README.md 참고.
"""

import os

import pytest
from playwright.sync_api import APIRequestContext, Playwright


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """backend 직접 호출용 base URL (nginx /backendApi/ 프리픽스 없음)."""
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture()
def api_request_context(
    playwright: Playwright, api_base_url: str
) -> APIRequestContext:
    """실제 backend에 REST로 직접 요청하는 컨텍스트(브라우저 없이)."""
    context = playwright.request.new_context(base_url=api_base_url)
    yield context
    context.dispose()
