"""mock-financial-service HTTP 클라이언트 — 계정계/정보계 API 경계.

ui_service 는 원장을 직접 만지지 않고 반드시 이 클라이언트를 거친다.
읽기는 정보계(analytics, X-Analytics-Key)로 수행한다(결정 C).

장애 격리(결정 D): 커넥션 실패/타임아웃/5xx/401 은 모두 FinancialServiceError
로 통일하고, 상위 예외 핸들러가 503 envelope 으로 번역한다. 계정계 장애가
백엔드 500 크래시로 전파되지 않는다. 404(계좌 없음)는 None/[] 로 번역해
"빈 상태"로 흡수한다.
"""

from __future__ import annotations

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from ...core.load_environment_var import settings
from ...core.resilience import MAX_RETRY_ATTEMPTS, call_with_retry
from ...utils.masking import mask_account_number
from ..dlq import enqueue_dlq
from .constants import _ACCOUNTS_PATH, _ANALYTICS_PREFIX, _TRANSFERS_PATH


class FinancialServiceError(Exception):
    """계정계 조회/변경 실패. 상위에서 503 envelope 으로 번역된다.

    `retryable`: 전송 오류·타임아웃·5xx 는 True(재시도 대상), 4xx 는 False(즉시 전파).
    `core/resilience.is_retryable` 이 이 값으로 재시도를 판정한다.
    """

    def __init__(self, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class FinancialServiceClient:
    """정보계 읽기 + 계정계 쓰기(추후) HTTP 구현.

    httpx.AsyncClient 는 재사용 가능한 커넥션 풀을 갖는다. 팩토리가 인스턴스를
    캐시하므로 프로세스당 풀 1개를 재사용한다.
    """

    def __init__(
        self,
        base_url: str,
        analytics_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(10.0, connect=3.0),
            headers={"X-Analytics-Key": analytics_key},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            # 로컬 IP/도메인 등 내부 주소가 로그로 새지 않도록 예외 문자열은
            # 타입명만 남긴다(CLAUDE.md 로깅 규칙). 전송 오류·타임아웃은 재시도 대상.
            raise FinancialServiceError(f"금융 서비스 연결 실패: {type(exc).__name__}", retryable=True) from exc

    async def get_balance(self, account_id: str) -> dict | None:
        """정보계 잔액 조회. 404 → None(계좌 없음)."""
        response = await self._request("GET", f"{_ANALYTICS_PREFIX}/accounts/{account_id}/balance")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise FinancialServiceError(f"잔액 조회 실패: HTTP {response.status_code}")
        return response.json()

    async def get_ledger(self, account_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """정보계 원장 항목 조회. 404 → []."""
        response = await self._request(
            "GET",
            f"{_ANALYTICS_PREFIX}/accounts/{account_id}/ledger",
            params={"limit": limit, "offset": offset},
        )
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise FinancialServiceError(f"원장 조회 실패: HTTP {response.status_code}")
        return response.json()

    async def get_cards(self, account_id: str) -> list[dict]:
        """정보계 계좌별 카드 목록 조회. 404 → []."""
        response = await self._request("GET", f"{_ANALYTICS_PREFIX}/accounts/{account_id}/cards")
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise FinancialServiceError(f"카드 목록 조회 실패: HTTP {response.status_code}")
        return response.json()

    async def get_card_ledger(self, card_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """정보계 카드 원장(구매내역) 조회. 404 → []."""
        response = await self._request(
            "GET",
            f"{_ANALYTICS_PREFIX}/cards/{card_id}/ledger",
            params={"limit": limit, "offset": offset},
        )
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise FinancialServiceError(f"카드 원장 조회 실패: HTTP {response.status_code}")
        return response.json()

    async def create_account(self, owner: str, initial_balance: int = 0) -> dict:
        """계정계 계좌 생성(POST /accounts, 무인증). 실패 시 FinancialServiceError.

        프로비저닝 전용. 반환 dict 의 account_id 를 로컬 매핑에 저장한다.
        """
        response = await self._request(
            "POST",
            _ACCOUNTS_PATH,
            json={"owner": owner, "initial_balance": initial_balance},
        )
        if response.status_code >= 400:
            raise FinancialServiceError(f"계좌 생성 실패: HTTP {response.status_code}")
        return response.json()

    async def _transfer_once(
        self,
        sender_account_number: str,
        receiver_bank_name: str,
        receiver_account_number: str,
        amount: int,
        idempotency_key: str,
    ) -> dict:
        response = await self._request(
            "POST",
            _TRANSFERS_PATH,
            json={
                "sender_account_number": sender_account_number,
                "receiver_bank_name": receiver_bank_name,
                "receiver_account_number": receiver_account_number,
                "amount": amount,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        if response.status_code >= 400:
            # 5xx 는 재시도, 4xx(검증·정책 위반)는 즉시 전파.
            raise FinancialServiceError(
                f"송금 실패: HTTP {response.status_code}",
                retryable=response.status_code >= 500,
            )
        return response.json()

    async def transfer(
        self,
        sender_account_number: str,
        receiver_bank_name: str,
        receiver_account_number: str,
        amount: int,
        idempotency_key: str,
    ) -> dict:
        """계정계 송금(POST /transfers). 계좌번호+은행명 기반(계정계 신 계약).

        Idempotency-Key 필수. 실패(4xx/5xx/커넥션)는 FinancialServiceError. 동일 키+
        동일 payload 재호출은 계정계가 기존 트랜잭션을 그대로 반환한다(safe replay).

        상태변경이라 **동일 Idempotency-Key 로 3회 인라인 재시도**하고(중복 이체 없음),
        재시도 소진 실패면 DLQ 에 적재한다(BE_Coding 1순위). DLQ 에는 마스킹 계좌·금액만.
        """
        try:
            return await call_with_retry(
                self._transfer_once,
                sender_account_number,
                receiver_bank_name,
                receiver_account_number,
                amount,
                idempotency_key,
            )
        except FinancialServiceError as exc:
            if exc.retryable:
                await enqueue_dlq(
                    kind="financial_transfer",
                    operation="transfer",
                    correlation_id=idempotency_key,
                    args={
                        "sender": mask_account_number(sender_account_number),
                        "receiver_bank": receiver_bank_name,
                        "receiver": mask_account_number(receiver_account_number),
                        "amount": amount,
                    },
                    attempts=MAX_RETRY_ATTEMPTS,
                    error_type=type(exc).__name__,
                )
            raise


# ── 프로세스당 단일 인스턴스(lazy) ────────────────────────────────────────────
_client: FinancialServiceClient | None = None


def get_financial_client() -> FinancialServiceClient:
    """계정계(정보계) 연동에 재사용하는 프로세스당 단일 클라이언트."""
    global _client
    if _client is None:
        _client = FinancialServiceClient(
            base_url=settings.MOCK_FINANCIAL_SERVICE_URL,
            analytics_key=settings.FINANCIAL_ANALYTICS_KEY.get_secret_value(),
        )
    return _client


async def close_financial_client() -> None:
    """lifespan 종료 시 커넥션 풀 정리."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def financial_service_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """계정계 장애를 503 envelope 으로 격리(결정 D)."""
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "error": {
                "code": "FINANCIAL_SERVICE_UNAVAILABLE",
                "message": "금융 서비스에 일시적으로 연결할 수 없습니다.",
            },
        },
    )
