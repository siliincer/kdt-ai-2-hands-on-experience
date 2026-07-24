"""계좌 추가(FE 슬래시 명령 `/add_account <은행명>`) DTO."""

from pydantic import BaseModel, Field


class AccountAddRequest(BaseModel):
    """POST /api/v1/accounts — 지정 은행의 부계좌 1개 추가."""

    bank_name: str = Field(min_length=1, max_length=50, description="추가할 계좌의 은행명")


class AccountAddData(BaseModel):
    """추가된 계좌의 최소 정보(마스킹된 계좌번호만 노출)."""

    account_id: str
    bank_name: str
    masked_account_number: str
    balance: int
    currency: str
