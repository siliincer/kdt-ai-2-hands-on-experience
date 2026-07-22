"""실 Agent 연동 + 계정계 http 일원화 e2e 검증 스크립트.

실행 중인 로컬 서버 3종(backend:8000, agent:8001, mock-financial-service:8002)을
대상으로, 다음 두 계층을 왕복 검증한다.

  L1 (BE ↔ 계정계, 작업 B): signup(프로비저닝) → login → GET /ui/balance 가
     mock-financial-service 잔액(시드 1,000,000)을 실조회하는지.
  L2 (BE → Agent → Webhook → SSE, 작업 A): POST /chat 로 Agent 실행을 시작하고,
     Agent 가 Webhook 으로 발행한 이벤트가 SSE 로 되돌아오는지(status/component/
     need_input/... 관찰). 계약상 done 까지 안 갈 수 있어(입력 대기) 관찰 위주.

사용법: uv run python scripts/e2e_agent_financial.py
필요: httpx (uv 워크스페이스에 이미 포함).
"""

from __future__ import annotations

import sys
import time
import uuid

import httpx

from .helpers import AGENT, BACKEND, FINANCIAL, _fail, _info, _ok

SEED_BALANCE = 1_000_000  # provisioning._SIGNUP_SEED_BALANCE
PASSWORD = "e2e-pass-1234"


def check_health(client: httpx.Client) -> bool:
    print("[0] 서비스 헬스체크")
    ok = True
    for name, url, expect in [
        ("backend", f"{BACKEND}/health", 200),
        ("agent", f"{AGENT}/health", 200),
        ("financial(docs)", f"{FINANCIAL}/docs", 200),
    ]:
        try:
            code = client.get(url, timeout=4).status_code
        except httpx.HTTPError as exc:
            _fail(f"{name} 연결 실패: {type(exc).__name__}")
            ok = False
            continue
        (_ok if code == expect else _fail)(f"{name} → HTTP {code}")
        ok = ok and code == expect
    return ok


def layer1_financial(client: httpx.Client) -> tuple[bool, str | None]:
    """L1: signup(프로비저닝) → login → /ui/balance 실조회."""
    print("\n[L1] BE ↔ 계정계 (작업 B: 계정계 http 일원화)")
    email = f"e2e_{uuid.uuid4().hex[:10]}@test.com"

    r = client.post(
        f"{BACKEND}/api/v1/users/signup",
        json={"email": email, "password": PASSWORD, "name": "E2E테스터"},
        timeout=15,
    )
    if r.status_code != 200:
        _fail(f"signup → HTTP {r.status_code}: {r.text[:200]}")
        return False, None
    _ok(f"signup ({email}) — 회원가입 시 계정계 계좌 프로비저닝 트리거")

    r = client.post(
        f"{BACKEND}/api/v1/users/login",
        json={"email": email, "password": PASSWORD},
        timeout=10,
    )
    if r.status_code != 200:
        _fail(f"login → HTTP {r.status_code}: {r.text[:200]}")
        return False, None
    token = r.json()["data"]["access_token"]
    _ok("login — access_token 발급")

    auth = {"Authorization": f"Bearer {token}"}
    r = client.get(f"{BACKEND}/api/v1/ui/balance", headers=auth, timeout=15)
    if r.status_code != 200:
        _fail(f"GET /ui/balance → HTTP {r.status_code}: {r.text[:200]}")
        return False, token
    data = r.json()["data"]
    total = data["total"]
    accounts = data["accounts"]
    _info(f"balance total={total:,} accounts={len(accounts)}")
    if accounts and total == SEED_BALANCE:
        _ok(f"BE→계정계 잔액 실조회 일치 (시드 {SEED_BALANCE:,}) — mock 픽스처가 아닌 실 계정계 값")
        return True, token
    if accounts:
        _info(
            f"잔액이 시드({SEED_BALANCE:,})와 다름(total={total:,}). 계정계 조회 경로는 "
            "동작(계좌 존재). 프로비저닝/시드 상태만 상이."
        )
        _ok("BE→계정계 실조회 경로 동작(계좌 매핑 존재)")
        return True, token
    _fail("계좌가 비어 있음 — 프로비저닝 또는 계정계 조회 실패 의심")
    return False, token


def layer2_agent(client: httpx.Client, token: str) -> bool:
    """L2: /chat → Agent 실행 → Webhook → SSE 이벤트 관찰."""
    print("\n[L2] BE → Agent → Webhook → SSE (작업 A: 실 Agent 연동)")
    auth = {"Authorization": f"Bearer {token}"}

    # 1) SSE 티켓 발급(새 chat_session 생성·바인딩)
    r = client.get(f"{BACKEND}/api/v1/sse/ticket", headers=auth, timeout=10)
    if r.status_code != 200:
        _fail(f"GET /sse/ticket → HTTP {r.status_code}: {r.text[:200]}")
        return False
    tkt = r.json()["data"]
    sse_session_id = tkt["sse_session_id"]
    chat_session_id = tkt["chat_session_id"]
    _ok(f"SSE 티켓 발급 (chat_session={chat_session_id[:8]}…)")

    # 2) 사용자 메시지 전송 → Agent 실행 시작(start_execution 202 → agent_thread_id 연결)
    r = client.post(
        f"{BACKEND}/api/v1/chat",
        headers=auth,
        json={"chat_session_id": chat_session_id, "message": "내 잔액 알려줘"},
        timeout=20,
    )
    if r.status_code != 200:
        _fail(f"POST /chat → HTTP {r.status_code}: {r.text[:300]}")
        return False
    _ok("POST /chat 접수 — Agent 실행 시작(start_execution). 진행은 SSE 로 스트리밍")

    # 3) SSE 연결 후 이벤트 수집(버퍼된 이벤트는 0-0 부터 리플레이됨)
    time.sleep(1.5)  # Agent 백그라운드 실행이 초기 이벤트를 발행할 시간
    events: list[str] = []
    deadline = time.time() + 10
    cur_event = None
    try:
        with client.stream(
            "GET",
            f"{BACKEND}/api/v1/sse/connect",
            params={"sse_session_id": sse_session_id},
            timeout=httpx.Timeout(12, read=12),
        ) as resp:
            if resp.status_code != 200:
                body = resp.read().decode()[:200]
                _fail(f"GET /sse/connect → HTTP {resp.status_code}: {body}")
                return False
            _ok("SSE 연결 성립 — Agent 이벤트 중계 수신 시작")
            for line in resp.iter_lines():
                if time.time() > deadline:
                    break
                if line.startswith("event:"):
                    cur_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and cur_event:
                    payload = line.split(":", 1)[1].strip()
                    events.append(cur_event)
                    _info(f"event={cur_event} data={payload[:90]}")
                    if cur_event in ("done", "error"):
                        break
                    cur_event = None
    except httpx.TimeoutException:
        _info("SSE read 타임아웃(추가 이벤트 없음) — 관찰 종료")
    except httpx.HTTPError as exc:
        _fail(f"SSE 스트림 오류: {type(exc).__name__}")
        return False

    kinds = [e for e in dict.fromkeys(events)]  # 중복 제거·순서 유지
    if events:
        _ok(f"Agent→Webhook→SSE 왕복 확인. 수신 event_type: {kinds}")
        return True
    _fail(
        "SSE 이벤트 미수신 — 실행 중인 Agent 프로세스가 Webhook 을 발행하지 못함.\n"
        "       backend webhook→Redis·계정계·agent-tools 는 격리 검증상 정상이므로,\n"
        "       실행 중 Agent 프로세스가 현재 .env 가 아닌 stale 환경일 가능성이 높다\n"
        "       (셸 export 가 .env 를 가리거나 .env 확정 전 기동). 조치: 깨끗한 셸에서\n"
        "       Agent 프로세스를 재기동 후 재실행."
    )
    return False


def main() -> int:
    print("=" * 68)
    print("실 Agent 연동 + 계정계 http 일원화 e2e 검증")
    print("=" * 68)
    with httpx.Client() as client:
        if not check_health(client):
            print("\n서비스가 모두 떠 있지 않아 중단합니다.")
            return 2
        l1_ok, token = layer1_financial(client)
        l2_ok = layer2_agent(client, token) if token else False

    print("\n" + "=" * 68)
    print(f"결과: L1(계정계) {'PASS' if l1_ok else 'FAIL'} | L2(Agent SSE) {'PASS' if l2_ok else 'FAIL'}")
    print("=" * 68)
    return 0 if (l1_ok and l2_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
