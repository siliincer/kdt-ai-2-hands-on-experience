"""Agent Tool API 응답 공통 컴포넌트.

여러 도메인 스키마에 중복 정의돼 있던 계좌 표시 정보·수정 안내 뷰를 모은다.
응답 JSON 필드는 기존과 동일하다(FE·Agent 영향 없음).
"""

from __future__ import annotations

from pydantic import BaseModel


class AccountDisplayRef(BaseModel):
    """승인/수정 화면의 계좌 표시 정보. 전체 계좌번호는 노출하지 않는다.

    기본계좌 변경·이체 화면 공용(구 AccountRef / TransferAccountRef).
    별칭 변경 화면은 계약 21.4상 별칭을 담지 않아 별도 스키마(AliasAccountRef)를 쓴다.
    """

    account_id: str
    bank_name: str | None
    account_alias: str | None
    masked_account_number: str


class CorrectionView(BaseModel):
    """수정으로 진행 가능한 경우의 안내 뷰(계약 14.5).

    Agent 는 reason 으로 추측하지 않고 allowed_change_targets 항목만 수정 UI 로 쓴다.
    허용 값은 Endpoint 별로 다르다(예: 이체 from_account/to_account/amount).
    """

    title: str | None = None
    allowed_change_targets: list[str]
