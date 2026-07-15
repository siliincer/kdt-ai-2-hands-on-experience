"""은행 데이터 클라이언트 — tool과 원장 사이의 API 경계.

tool은 원장(mock_bank)을 직접 만지지 않고 반드시 이 클라이언트를 거친다.
시트 API Spec 탭의 REST 계약을 따르며, 구현은 환경변수로 전환한다:

  BANK_CLIENT=local (기본): agent 내장 mock 원장을 직접 다룬다.
                            외부 의존 없음 — 테스트/노트북 기본 경로.
  BANK_CLIENT=http:         mock-financial-service(8002)를 HTTP로 호출한다.
                            docker compose가 이 모드를 켠다.

에러 계약: 조회/변경 실패는 BankClientError로 통일한다. tool은 이 예외를
잡아 error/failed 라우트로 보낸다 (그래프 크래시 금지).
"""

from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import Protocol

import httpx

from agent.data.mock_bank import (
    AUDIT_LOG,
    MOCK_ACCOUNTS,
    MOCK_RECIPIENTS,
    MOCK_TRANSACTIONS,
)


class BankClientError(Exception):
    """원장 조회/변경 실패. tool은 이 예외를 잡아 실패 라우트로 보낸다."""


class BankClient(Protocol):
    """은행 데이터 접근 계약 (시트 API Spec 탭 기준)."""

    def get_accounts(
        self, user_id: str, account_id: str | None = None
    ) -> list[dict]: ...

    def get_recipients(
        self, user_id: str, recipient_name: str | None = None
    ) -> list[dict]: ...

    def get_transactions(
        self,
        user_id: str,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]: ...

    def transfer(
        self,
        user_id: str,
        from_account_id: str,
        to_recipient_id: str,
        amount: int,
        memo: str | None = None,
    ) -> dict: ...

    def transfer_internal(
        self, user_id: str, from_account_id: str, to_account_id: str, amount: int
    ) -> dict: ...

    def post_audit_log(
        self,
        event_type: str,
        workflow_id: str | None,
        tool_id: str | None,
        result: dict,
    ) -> dict: ...

    def set_default_account(self, user_id: str, account_id: str) -> dict: ...

    def set_account_alias(self, user_id: str, account_id: str, alias: str) -> dict: ...


class LocalBankClient:
    """인메모리 mock 원장 구현 (외부 의존 없음)."""

    def get_accounts(self, user_id: str, account_id: str | None = None) -> list[dict]:
        # 주의: live dict를 그대로 반환한다 (복사 금지).
        # transfer의 in-place 잔액 차감과 _live_account 재조회 의미론이
        # 이 참조 공유에 의존한다 (test_bank_client의 identity 테스트가 고정).
        accounts = MOCK_ACCOUNTS.get(user_id, [])
        if account_id:
            return [a for a in accounts if a.get("account_id") == account_id]
        return accounts

    def get_recipients(
        self, user_id: str, recipient_name: str | None = None
    ) -> list[dict]:
        recipients = MOCK_RECIPIENTS.get(user_id, [])
        if recipient_name:
            return [r for r in recipients if recipient_name in r.get("name", "")]
        return recipients

    def get_transactions(
        self,
        user_id: str,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        results = MOCK_TRANSACTIONS.get(user_id, [])
        if account_id:
            results = [t for t in results if t.get("account_id") == account_id]
        if start_date:
            results = [t for t in results if t.get("date", "") >= start_date]
        if end_date:
            results = [t for t in results if t.get("date", "") <= end_date]
        return sorted(results, key=lambda t: t.get("date", ""), reverse=True)

    def transfer(
        self,
        user_id: str,
        from_account_id: str,
        to_recipient_id: str,
        amount: int,
        memo: str | None = None,
    ) -> dict:
        account = next(
            (
                a
                for a in MOCK_ACCOUNTS.get(user_id, [])
                if a.get("account_id") == from_account_id
            ),
            None,
        )
        if account is None:
            raise BankClientError("출금 계좌를 찾을 수 없습니다.")
        recipients = MOCK_RECIPIENTS.get(user_id, [])
        if not any(r.get("recipient_id") == to_recipient_id for r in recipients):
            raise BankClientError("수취인을 찾을 수 없습니다.")
        if account["balance"] < amount:
            raise BankClientError("잔액이 부족합니다.")

        account["balance"] -= amount  # mock 원장의 유일한 승인된 변형

        return {
            "transaction_id": f"txn_{uuid.uuid4().hex[:8]}",
            "status": "completed",
        }

    def transfer_internal(
        self, user_id: str, from_account_id: str, to_account_id: str, amount: int
    ) -> dict:
        accounts = MOCK_ACCOUNTS.get(user_id, [])
        from_account = next(
            (a for a in accounts if a.get("account_id") == from_account_id), None
        )
        to_account = next(
            (a for a in accounts if a.get("account_id") == to_account_id), None
        )
        if from_account is None or to_account is None:
            raise BankClientError("계좌를 찾을 수 없습니다.")
        if from_account["balance"] < amount:
            raise BankClientError("잔액이 부족합니다.")

        from_account["balance"] -= amount
        to_account["balance"] += amount

        return {
            "transaction_id": f"txn_{uuid.uuid4().hex[:8]}",
            "status": "completed",
        }

    def post_audit_log(
        self,
        event_type: str,
        workflow_id: str | None,
        tool_id: str | None,
        result: dict,
    ) -> dict:
        entry = {
            "event_type": event_type,
            "workflow_id": workflow_id,
            "tool_id": tool_id,
            "result": result,
        }
        AUDIT_LOG.append(entry)
        return {"log_id": f"local_log_{len(AUDIT_LOG):04d}"}

    def set_default_account(self, user_id: str, account_id: str) -> dict:
        """대상 계좌를 기본 출금계좌로 지정하고 나머지는 해제한다 (in-place)."""
        accounts = MOCK_ACCOUNTS.get(user_id, [])
        target = next((a for a in accounts if a.get("account_id") == account_id), None)
        if target is None:
            raise BankClientError(f"계좌를 찾을 수 없습니다: {account_id}")
        for a in accounts:
            a["is_default"] = a.get("account_id") == account_id
        return {"account_id": account_id, "is_default": True}

    def set_account_alias(self, user_id: str, account_id: str, alias: str) -> dict:
        """대상 계좌의 별칭을 설정한다 (in-place)."""
        accounts = MOCK_ACCOUNTS.get(user_id, [])
        target = next((a for a in accounts if a.get("account_id") == account_id), None)
        if target is None:
            raise BankClientError(f"계좌를 찾을 수 없습니다: {account_id}")
        target["alias"] = alias
        return {"account_id": account_id, "alias": alias}


class HttpBankClient:
    """mock-financial-service HTTP 구현 (시트 API Spec 계약).

    httpx.Client는 스레드 세이프하고 팩토리가 인스턴스를 캐시하므로
    프로세스당 커넥션 풀 1개를 재사용한다.
    """

    def __init__(
        self, base_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(10.0, connect=3.0),
            transport=transport,
        )

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise BankClientError(f"은행 서비스 연결 실패: {exc}") from exc

    def get_accounts(self, user_id: str, account_id: str | None = None) -> list[dict]:
        params = {"account_id": account_id} if account_id else None
        response = self._request("GET", f"/api/accounts/{user_id}", params=params)
        if response.status_code == 404:
            # 로컬 모드의 not_found 라우트 의미 보존 (빈 목록으로 번역)
            return []
        if response.status_code >= 400:
            raise BankClientError(f"계좌 조회 실패: HTTP {response.status_code}")
        return response.json().get("accounts", [])

    def get_recipients(
        self, user_id: str, recipient_name: str | None = None
    ) -> list[dict]:
        params: dict = {"user_id": user_id}
        if recipient_name:
            params["recipient_name"] = recipient_name
        response = self._request("GET", "/api/recipients", params=params)
        if response.status_code >= 400:
            raise BankClientError(f"수취인 조회 실패: HTTP {response.status_code}")
        return response.json().get("recipient_candidates", [])

    def get_transactions(
        self,
        user_id: str,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        params: dict = {"user_id": user_id}
        if account_id:
            params["account_id"] = account_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        response = self._request("GET", "/api/transactions", params=params)
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise BankClientError(f"거래내역 조회 실패: HTTP {response.status_code}")
        return response.json().get("transactions", [])

    def transfer(
        self,
        user_id: str,
        from_account_id: str,
        to_recipient_id: str,
        amount: int,
        memo: str | None = None,
    ) -> dict:
        body = {
            "user_id": user_id,
            "from_account_id": from_account_id,
            "to_recipient_id": to_recipient_id,
            "amount": amount,
            "memo": memo,
        }
        response = self._request(
            "POST", "/api/transactions/transfer-external", json=body
        )
        if response.status_code >= 400:
            raise BankClientError(f"송금 실행 실패: HTTP {response.status_code}")
        return response.json()

    def transfer_internal(
        self, user_id: str, from_account_id: str, to_account_id: str, amount: int
    ) -> dict:
        body = {
            "user_id": user_id,
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "amount": amount,
        }
        response = self._request(
            "POST", "/api/transactions/transfer-internal", json=body
        )
        if response.status_code >= 400:
            raise BankClientError(f"본인이체 실행 실패: HTTP {response.status_code}")
        return response.json()

    def post_audit_log(
        self,
        event_type: str,
        workflow_id: str | None,
        tool_id: str | None,
        result: dict,
    ) -> dict:
        body = {
            "event_type": event_type,
            "workflow_id": workflow_id,
            "tool_id": tool_id,
            "result": result,
        }
        response = self._request("POST", "/api/audit-logs", json=body)
        if response.status_code >= 400:
            raise BankClientError(f"감사 로그 전송 실패: HTTP {response.status_code}")
        return response.json()

    def set_default_account(self, user_id: str, account_id: str) -> dict:
        body = {"user_id": user_id, "account_id": account_id}
        response = self._request("POST", "/api/accounts/default", json=body)
        if response.status_code >= 400:
            raise BankClientError(f"기본계좌 설정 실패: HTTP {response.status_code}")
        return response.json()

    def set_account_alias(self, user_id: str, account_id: str, alias: str) -> dict:
        body = {"user_id": user_id, "account_id": account_id, "alias": alias}
        response = self._request("POST", "/api/accounts/alias", json=body)
        if response.status_code >= 400:
            raise BankClientError(f"별칭 설정 실패: HTTP {response.status_code}")
        return response.json()


@lru_cache(maxsize=1)
def get_bank_client() -> BankClient:
    """BANK_CLIENT 환경변수로 구현을 선택한다 (기본 local).

    테스트에서 모드를 바꾸려면 get_bank_client.cache_clear()를 호출한다.
    """
    if os.getenv("BANK_CLIENT", "local").strip().lower() == "http":
        base_url = os.getenv("MOCK_FINANCIAL_SERVICE_URL", "http://localhost:8002")
        return HttpBankClient(base_url=base_url)
    return LocalBankClient()
