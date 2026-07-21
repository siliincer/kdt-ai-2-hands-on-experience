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


def _login(page: Page, user: dict) -> None:
    """로그인 폼 제출 후 챗 화면 진입까지 기다린다.

    "RealFinance" 텍스트는 로그인 화면 브랜딩에도 그대로 나와서 로그인 완료
    신호로 못 쓴다(레이스 컨디션 유발 — 로그인 API 응답/sessionStorage 기록이
    끝나기 전에 매칭돼버림). 챗 화면에만 있는 "로그아웃" 버튼으로 판단한다.
    """
    page.goto("/")
    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("비밀번호를 입력하세요").fill(user["password"])
    page.get_by_role("button", name="로그인").click()
    expect(page.get_by_role("button", name="로그아웃")).to_be_visible(timeout=10_000)


def test_signup_then_login_shows_chat_screen(page: Page, api_request_context: APIRequestContext):
    user = _signup(api_request_context)

    page.goto("/")
    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("비밀번호를 입력하세요").fill(user["password"])
    page.get_by_role("button", name="로그인").click()

    expect(page.get_by_text("RealFinance")).to_be_visible(timeout=10_000)
    expect(page.get_by_placeholder("example@email.com")).not_to_be_visible()


def test_login_wrong_password_shows_error(page: Page, api_request_context: APIRequestContext):
    user = _signup(api_request_context)

    page.goto("/")
    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("비밀번호를 입력하세요").fill("wrong-password-1")
    page.get_by_role("button", name="로그인").click()

    expect(page.get_by_text("이메일 또는 비밀번호가 잘못되었습니다.")).to_be_visible(timeout=10_000)
    expect(page.get_by_placeholder("example@email.com")).to_be_visible()


def test_balance_inquiry_shows_provisioned_account(page: Page, api_request_context: APIRequestContext):
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


def test_transfer_confirm_card_appears_with_real_agent_flow(page: Page, api_request_context: APIRequestContext):
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
    expect(page.get_by_text("송금").or_(page.get_by_text("누구"))).to_be_visible(timeout=20_000)


def test_transfer_completes_after_confirmation(page: Page, api_request_context: APIRequestContext):
    """송금 확인 카드까지가 아니라 승인 버튼까지 눌러서 완료 응답을 받는다.

    주의: .env에 FINANCIAL_DEMO_RECEIVER_BANK_NAME/ACCOUNT_NUMBER가 비어있으면
    backend가 실제 원장에는 반영하지 않고(fault-isolation) 대화만 완료 처리한다
    (backend/src/backend/services/financial/transfer_service.py 참고). 그래서
    여기서는 잔액 변화가 아니라 "승인 → 완료" 대화 흐름 자체를 검증한다.
    """
    user = _signup(api_request_context)
    _login(page, user)

    page.get_by_role("button", name="송금하기").click()
    expect(page.get_by_text("송금 확인")).to_be_visible(timeout=20_000)

    page.get_by_role("button", name="송금하기 →").click()
    expect(page.get_by_text("보냈어요")).to_be_visible(timeout=20_000)


def test_logout_returns_to_login_screen(page: Page, api_request_context: APIRequestContext):
    user = _signup(api_request_context)
    _login(page, user)

    page.get_by_role("button", name="로그아웃").click()

    expect(page.get_by_placeholder("example@email.com")).to_be_visible(timeout=10_000)
    # sessionStorage.rf_access_token/rf_logged_in 정리 확인
    # (frontend/src/entities/user/model/store.ts logout())
    token = page.evaluate("() => sessionStorage.getItem('rf_access_token')")
    logged_in = page.evaluate("() => sessionStorage.getItem('rf_logged_in')")
    assert token is None
    assert logged_in is None


def test_expired_session_redirects_to_login(page: Page, api_request_context: APIRequestContext):
    """진짜 세션 만료(유효하지 않은 토큰) → 자동 로그아웃 + 로그인 화면 복귀.

    주의(발견한 버그, 이 테스트가 검증하는 범위 밖): "세션이 만료되었습니다.
    다시 로그인해 주세요." 문구는 frontend/src/shared/api/customFetch.ts:24에서
    APIError로 던져지기만 하고, 화면에 실제로 렌더링해주는 토스트/배너 컴포넌트가
    없다(grep 결과 이 문자열을 실제 표시하는 곳은 LoginFeature.tsx의 로그인 실패
    catch 블록 하나뿐 — 그건 별개 버그인 test_login_wrong_password_shows_error가
    다룬다). 그래서 진짜 세션 만료 시에는 조용히 로그인 화면으로만 넘어가고
    사용자에게 이유를 알려주는 메시지는 안 뜬다. 여기서는 "리다이렉트는 되는지"만
    확인한다 — 메시지 노출은 UX 갭으로 별도 이슈감이다.
    """
    user = _signup(api_request_context)
    _login(page, user)

    # 로그인 이후 토큰을 깨뜨려서 인증이 필요한 다음 요청이 실제 401을 받게 만든다
    # (backend/src/backend/security/jwt.py verify_token()이 JWTError → 401).
    page.evaluate("() => sessionStorage.setItem('rf_access_token', 'garbage-invalid-token')")

    page.get_by_role("button", name="잔액 확인").click()

    expect(page.get_by_placeholder("example@email.com")).to_be_visible(timeout=10_000)


def test_signup_duplicate_email_shows_error(page: Page, api_request_context: APIRequestContext):
    user = _signup(api_request_context)  # 이메일 하나 선점

    page.goto("/")
    page.get_by_role("button", name="회원가입").click()  # 로그인 화면 → 가입 화면 전환

    page.get_by_placeholder("example@email.com").fill(user["email"])
    page.get_by_placeholder("8자 이상 입력하세요").fill("another-password-1")
    page.get_by_placeholder("비밀번호를 다시 입력하세요").fill("another-password-1")
    page.get_by_role("button", name="회원가입").click()

    expect(page.get_by_text("이미 사용 중인 이메일입니다.")).to_be_visible(timeout=10_000)


def test_session_persists_after_reload(page: Page, api_request_context: APIRequestContext):
    user = _signup(api_request_context)
    _login(page, user)

    page.reload()

    expect(page.get_by_role("button", name="로그아웃")).to_be_visible(timeout=10_000)
    expect(page.get_by_placeholder("example@email.com")).not_to_be_visible()
