"""신규 수취 계좌 검증 DTO (Frontend 전용, D5 / 계약 부록 29.2).

Frontend 가 은행·계좌번호 원문을 이 API 까지만 제출하고, 응답으로 원문 대신
`recipient_candidate_id` 참조를 받는다. Agent·Tool API 는 이 참조만 사용한다.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RecipientCandidateVerifyRequest(BaseModel):
    chat_session_id: UUID
    # 단일 은행 샌드박스(D6)라 은행 식별은 선택. 주어지면 일치 여부를 검증한다.
    bank_name: str | None = Field(default=None, max_length=50)
    account_number: str = Field(min_length=1, max_length=30)


class RecipientCandidateVerifyData(BaseModel):
    recipient_candidate_id: str
    # 예금주명은 마스킹해 반환한다("홍*동"). 원문은 응답에 포함하지 않는다.
    name: str
    bank_name: str | None
    masked_account_number: str
    status: str
    expires_at: datetime
