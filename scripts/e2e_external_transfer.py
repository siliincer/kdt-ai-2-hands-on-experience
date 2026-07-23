"""타인송금(external transfer) 워크플로우 라이브 e2e 드라이버.

실행 중인 backend(8000)+agent(8001)+계정계(8002) 대상. 타인송금은 다단계 HITL:
  recipient_select(need_input) → 승인(need_approval) → 추가 인증(authentication_required)
  → 실행(Execute) → done. 각 정지점을 이벤트로 관찰하고 반응형으로 회신한다.

수취인 검증(POST /recipient-candidates:verify)은 "동일은행 타 owner"(다른 로컬 사용자)
계좌번호로만 통과하므로, 먼저 수취인 사용자를 만들어 그 계좌번호를 사용한다.

사용법: uv run python scripts/e2e_external_transfer.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import httpx
import redis.asyncio as aioredis
from helpers import BACKEND, _as_str, _fail, _info, _ok

from backend.core.load_environment_var import settings

PW = "e2e-pass-1234"
AMOUNT = 50_000


async def _signup_login(c: httpx.AsyncClient, name: str) -> tuple[str, str]:
    email = f"xf_{uuid.uuid4().hex[:10]}@test.com"
    await c.post(
        f"{BACKEND}/api/v1/users/signup",
        json={"email": email, "password": PW, "name": name},
        timeout=15,
    )
    r = await c.post(
        f"{BACKEND}/api/v1/users/login",
        json={"email": email, "password": PW},
        timeout=10,
    )
    d = r.json()["data"]
    return d["user"]["id"], d["access_token"]


async def _recipient_account_number(user_id: str) -> tuple[str, str | None]:
    """수취인 사용자의 프로비저닝 계좌번호·은행명을 DB 에서 읽는다."""
    from backend.db.postgres import AsyncSessionLocal
    from backend.repository.account_repository import get_mapped_accounts

    async with AsyncSessionLocal() as s:
        rows = await get_mapped_accounts(s, uuid.UUID(user_id))
    if not rows:
        raise RuntimeError("수취인 계좌 프로비저닝 실패")
    return rows[0].account_number, rows[0].bank_name


class StreamReader:
    """agent:stream 을 순서대로 읽어 다음 이벤트를 돌려주는 커서."""

    def __init__(self, redis: aioredis.Redis, chat_session_id: str) -> None:
        self._redis = redis
        self._key = f"agent:stream:{chat_session_id}"
        self._seen = 0

    async def next_events(self, deadline_s: float = 20.0) -> list[dict]:
        loop = asyncio.get_event_loop()
        end = loop.time() + deadline_s
        while loop.time() < end:
            entries = await self._redis.xrange(self._key, count=100)
            # None 방어 코드 추가 (entries가 None이면 빈 리스트로 초기화)
            if entries is None:
                entries = []

            if len(entries) > self._seen:
                fresh = entries[self._seen :]
                self._seen = len(entries)
                out = []
                for _eid, fields in fresh:
                    # fields가 None일 경우 빈 딕셔너리로 대체
                    if fields is None:
                        fields = {}

                    # redis 설정에 따라 bytes 또는 str 로 오므로 둘 다 처리한다.
                    d = {_as_str(k): _as_str(v) for k, v in fields.items()}

                    d["metadata"] = json.loads(d.get("metadata") or "{}")
                    out.append(d)
                return out
            await asyncio.sleep(1.0)
        return []


async def _drive(
    c: httpx.AsyncClient,
    reader: StreamReader,
    auth: dict,
    cs: str,
    recipient_candidate_id: str,
) -> bool:
    """정지점(need_input/need_approval/authentication_required)에 반응해 완료까지 진행."""
    for _step in range(12):
        events = await reader.next_events()
        if not events:
            _fail("이벤트 타임아웃 — 진행 멈춤")
            return False
        for ev in events:
            et = ev["event_type"]
            md = ev["metadata"]
            if et in ("status", "token", "tool_call", "component"):
                label = md.get("ui_contract_id") or md.get("step_id") or ""
                _info(f"event={et} {label} {(ev.get('content') or '')[:30]}")
                continue
            if et == "done":
                _ok("done — 타인송금 워크플로우 종료")
                return True
            if et == "error":
                _fail(f"error: {(ev.get('content') or '')[:80]} (step={md.get('step_id')})")
                return False
            if et == "need_input":
                irid = md.get("input_request_id")
                ui_type = md.get("ui", {}).get("type")
                _info(f"need_input ui={ui_type} irid={irid}")
                value = _input_value_for(ui_type, recipient_candidate_id)
                r = await c.post(
                    f"{BACKEND}/api/v1/agent/input",
                    headers=auth,
                    json={"chat_session_id": cs, "input_request_id": irid, "value": value},
                    timeout=20,
                )
                _info(f"→ POST /agent/input ({ui_type}) {r.status_code}")
            elif et == "need_approval":
                approval_id = ev.get("approval_id")
                _info(f"need_approval approval_id={(approval_id or '')[:8]}…")
                r = await c.post(
                    f"{BACKEND}/api/v1/agent/approve",
                    headers=auth,
                    json={
                        "chat_session_id": cs,
                        "approval_id": approval_id,
                        "decision": "approve",
                        "component": "external_transfer",
                    },
                    timeout=20,
                )
                _info(f"→ POST /agent/approve (approve) {r.status_code}")
            elif et == "authentication_required":
                auth_context_id = md.get("auth_context_id")
                _info(f"authentication_required auth_context_id={(auth_context_id or '')[:8]}…")
                r = await c.post(
                    f"{BACKEND}/api/v1/agent/authenticate",
                    headers=auth,
                    json={"chat_session_id": cs, "auth_context_id": auth_context_id, "password": PW},
                    timeout=20,
                )
                body = r.json().get("data", {})
                _info(f"→ POST /agent/authenticate {r.status_code} auth_status={body.get('auth_status')}")
    _fail("최대 스텝 초과 — done 도달 실패")
    return False


def _input_value_for(ui_type: str | None, recipient_candidate_id: str) -> dict:
    if ui_type == "recipient_select":
        return {
            "recipient_selection_outcome": "selected",
            "to_recipient_id": None,
            "to_recipient_candidate_id": recipient_candidate_id,
        }
    if ui_type == "number_input":
        return {"amount_input_outcome": "submitted", "amount": AMOUNT}
    if ui_type == "account_card_list":
        # from-account 선택(단일 계좌면 보통 자동 resolved 지만 방어적으로 처리)
        return {"account_selection_outcome": "cancelled"}
    return {}


async def main() -> int:
    print("=" * 68)
    print("타인송금(external transfer) 라이브 e2e")
    print("=" * 68)
    async with httpx.AsyncClient() as c:
        # 1) 수취인 사용자(계좌번호 확보) + 송금인 사용자
        rcpt_id, _ = await _signup_login(c, "홍길동")
        acct_no, bank = await _recipient_account_number(rcpt_id)
        _ok(f"수취인 준비 (계좌 {acct_no[-4:]}··· / {bank})")

        sender_id, token = await _signup_login(c, "김철수")
        auth = {"Authorization": f"Bearer {token}"}
        _ok("송금인 준비 (프로비저닝 계좌 1,000,000)")

        # 2) SSE 티켓 → chat_session
        r = await c.get(f"{BACKEND}/api/v1/sse/ticket", headers=auth, timeout=10)
        cs = r.json()["data"]["chat_session_id"]

        # 3) 송금 시작
        r = await c.post(
            f"{BACKEND}/api/v1/chat",
            headers=auth,
            json={"chat_session_id": cs, "message": f"홍길동에게 {AMOUNT}원 송금해줘"},
            timeout=20,
        )
        if r.status_code != 200:
            _fail(f"POST /chat {r.status_code}: {r.text[:200]}")
            return 1
        _ok("POST /chat 접수 — 타인송금 실행 시작")

        # 4) 수취인 후보 검증(계좌번호 → to_recipient_candidate_id)
        r = await c.post(
            f"{BACKEND}/api/v1/recipient-candidates:verify",
            headers=auth,
            json={"chat_session_id": cs, "bank_name": bank, "account_number": acct_no},
            timeout=15,
        )
        if r.status_code != 200:
            _fail(f"recipient verify {r.status_code}: {r.text[:200]}")
            return 1
        rc_id = r.json()["data"]["recipient_candidate_id"]
        _ok(f"수취인 검증 → to_recipient_candidate_id={rc_id[:10]}…")

        # 5) HITL 루프 구동
        redis = aioredis.from_url(str(settings.REDIS_STREAM_URL))
        reader = StreamReader(redis, cs)
        ok = await _drive(c, reader, auth, cs, rc_id)
        await redis.aclose()

    print("\n" + "=" * 68)
    print(f"결과: 타인송금 e2e {'PASS' if ok else 'FAIL'}")
    print("=" * 68)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
