"""금융 정책 상수 (D7: 정책 테이블 대신 상수 모듈로 시작).

Prepare/Execute 의 `correction_required`·`blocked` 판정 근거가 되는 값을 한곳에 모은다.
계정계에는 한도·수수료·hold 개념이 없으므로 판정은 Backend 책임이다.

값은 데모 기준의 임시값이며 조정 가능하다. 사용자·계좌별로 달라져야 하면 policy 테이블로
승격한다(현재 범위 아님).
"""

from __future__ import annotations

# ── Confirmation ─────────────────────────────────────────────────────────────
# Prepare 가 고정한 승인 대상의 유효시간. 계약 예시(expires_at)가 약 5분이라 300초.
CONFIRMATION_TTL_SECONDS = 300

# ── 멱등성 ───────────────────────────────────────────────────────────────────
# 멱등성 결과 보존 기간. 계약 24.3 예시가 생성 후 약 24시간.
IDEMPOTENCY_TTL_SECONDS = 86_400

# ── 계좌 별칭 정책 (API-ACCOUNT-ALIAS-*) ─────────────────────────────────────
ALIAS_MIN_LENGTH = 1
ALIAS_MAX_LENGTH = 20
# 금지 표현. 데모용 최소 집합이며 정규화(공백 정리·소문자) 후 부분 일치로 검사한다.
ALIAS_FORBIDDEN_WORDS: tuple[str, ...] = ("admin", "관리자", "테스트")

# ── 이체 정책 (Stage 5·6 의 내부이체·타인송금에서 사용) ──────────────────────
# 현재 범위에서 수수료는 0원 고정.
TRANSFER_FEE_KRW = 0
# 1회 및 일일 이체 한도. 초과 시 correction_required(limit_exceeded).
MAX_SINGLE_TRANSFER_KRW = 5_000_000
MAX_DAILY_TRANSFER_KRW = 10_000_000


def normalize_alias(alias: str) -> str:
    """별칭 정규화: 앞뒤 공백 제거 + 연속 공백 1칸으로 축약.

    `unchanged` 판정(현재 별칭과 같은지)과 중복 검사는 이 정규화 결과로 비교한다.
    """
    return " ".join(alias.split())


def is_alias_forbidden(alias: str) -> bool:
    """금지 표현 포함 여부(대소문자 무시)."""
    lowered = normalize_alias(alias).lower()
    return any(word.lower() in lowered for word in ALIAS_FORBIDDEN_WORDS)
