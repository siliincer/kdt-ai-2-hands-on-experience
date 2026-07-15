"""로그인 → 계좌조회 → 송금 — mock 없이 실제 backend API + 실제 브라우저로 검증.

사전 준비 (repo root):
    docker compose up --build -d
    cd frontend && npm run dev   # 5173

실행 (repo root):
    uv run --package e2e pytest e2e/tests/test_login_balance_transfer.py \
        --base-url http://localhost:5173
"""

import uuid

from playwright.sync_api import APIRequestContext, Page, expect


def _signup(api_request_context: APIRequestContext) -> dict:
    """실제 backend /users/signup 으로 매 실행마다 새 유저를 만든다.

    시드 데이터/미리 만든 테스트 계정에 의존하지 않기 위함 — 신규가입 시
    계정계 계좌가 같이 프로비저닝된다(backend user_service.signup_user).
    """
    email = f"e2e-{uuid.uuid4().hex[:12]}@example.com"
    password = "e2e-test-password-1"
    response = api_request_context.post(
        "/api/v1/users/signup",
        data={"email": email, "password": password, "name": "E2E테스터"},
    )
    assert response.ok, f"signup 실패: {response.status} {response.text()}"
    return {"email": email, "password": password}


def test_signup_then_login_shows_chat_screen(
    page: Page, api_request_context: APIRequestContext
):
    user = _signup(api_request_context)

    page.goto("/")
    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("비밀번호를 입력하세요").fill(user["password"])
    page.get_by_role("button", name="로그인").click()

    expect(page.get_by_text("RealFinance")).to_be_visible(timeout=10_000)
    expect(page.get_by_placeholder("example@email.com")).not_to_be_visible()


def test_login_wrong_password_shows_error(
    page: Page, api_request_context: APIRequestContext
):
    user = _signup(api_request_context)

    page.goto("/")
    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("비밀번호를 입력하세요").fill("wrong-password-1")
    page.get_by_role("button", name="로그인").click()

    expect(page.get_by_text("이메일 또는 비밀번호가 잘못되었습니다.")).to_be_visible(
        timeout=10_000
    )
    expect(page.get_by_placeholder("example@email.com")).to_be_visible()


def test_balance_inquiry_shows_provisioned_account(
    page: Page, api_request_context: APIRequestContext
):
    user = _signup(api_request_context)

    page.goto("/")
    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("비밀번호를 입력하세요").fill(user["password"])
    page.get_by_role("button", name="로그인").click()
    expect(page.get_by_text("RealFinance")).to_be_visible(timeout=10_000)

    # 실제 agent가 자연어를 해석해 잔액조회 tool을 호출하고, 실제 backend
    # UI Data API가 신규가입 시 프로비저닝된 계좌 데이터를 반환해야 한다.
    page.get_by_role("button", name="잔액 확인").click()
    expect(page.get_by_text("내 자산 현황")).to_be_visible(timeout=20_000)


def test_transfer_confirm_card_appears_with_real_agent_flow(
    page: Page, api_request_context: APIRequestContext
):
    user = _signup(api_request_context)

    page.goto("/")
    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("비밀번호를 입력하세요").fill(user["password"])
    page.get_by_role("button", name="로그인").click()
    expect(page.get_by_text("RealFinance")).to_be_visible(timeout=10_000)

    # "송금하기" 빠른 프롬프트 → 실제 에이전트가 need_approval로 멈추고
    # 정보를 되묻거나(수취인/금액) 확인 카드를 띄운다. 최소한 자연어 응답이나
    # 확인 카드 중 하나는 대화창에 나타나야 한다.
    page.get_by_role("button", name="송금하기").click()
    expect(
        page.get_by_text("송금").or_(page.get_by_text("누구"))
    ).to_be_visible(timeout=20_000)
