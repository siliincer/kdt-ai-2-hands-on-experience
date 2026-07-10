"""에이전트 채팅 API 요청/응답 스키마 — 프론트/백엔드와의 계약 소유처.

에이전트는 내부 서비스이므로 plain JSON을 반환한다.
backend 게이트웨이가 이 응답을 CommonResponse(success/message/data)로 감싼다.

계약 확인 방법:
  - 이 파일의 타입 (특히 ChatUi 5종 — frontend types.ts와 1:1 대응)
  - 서버 실행 후 http://localhost:8001/docs (OpenAPI 자동 노출)
  - agent/tests/test_ui_contract.py (계약 강제 테스트)
  - 문서: agent/docs/README.md 3절 (파트별 명령형 스펙)
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

ChatStatus = Literal["completed", "waiting_input", "blocked", "no_match", "failed"]


# ── 구조화 UI 힌트 (waiting_input 응답의 ui 필드) ─────────────────────────────
#
# 공통 규약:
#   - ui가 null이면 reply 텍스트 말풍선으로 폴백 렌더링한다.
#   - 사용자의 선택/버튼 클릭은 별도 필드가 아니라 **다음 요청의 message에
#     그 라벨 문자열을 그대로** 담아 회신한다 (예: "송금하기", "1번", "취소").
#   - 필드 추가는 하위 호환(extra="allow")이지만 제거/개명은 계약 파괴다.


class _UiBase(BaseModel):
    model_config = ConfigDict(extra="allow")


class AccountCardOption(_UiBase):
    account_id: str
    account_name: str
    balance: int


class AccountCardListUi(_UiBase):
    """계좌 카드 목록에서 선택. multi=true면 복수 선택('1번이랑 2번') 허용."""

    type: Literal["account_card_list"]
    options: list[AccountCardOption]
    multi: bool | None = Field(None, description="복수 선택 가능 여부 (없으면 단일)")


class RecipientOption(_UiBase):
    recipient_id: str
    name: str
    bank: str
    account_number: str


class SearchSelectUi(_UiBase):
    """수취인 검색/선택. 목록에 없는 이름·계좌번호 직접 입력도 허용된다."""

    type: Literal["search_select"]
    options: list[RecipientOption]


class NumberInputUi(_UiBase):
    """금액 입력. '5만원' 같은 자연어도 허용된다 (서버가 정규화)."""

    type: Literal["number_input"]


class ConfirmModalUi(_UiBase):
    """확인 모달 — 돈이 움직이는 최종 게이트.

    반드시 명시적 승인 UI로 렌더링해야 하며 자동 확인은 금지다.
    variant="warning"은 고액/신규 수취인 주의 안내(확인/취소),
    variant 없음은 송금 승인 카드(display 5필드 + 수정 액션 포함)다.
    """

    type: Literal["confirm_modal"]
    variant: str | None = Field(None, description='"warning" | 없음(승인 카드)')
    display: dict = Field(description="카드에 표시할 필드 (variant별로 다름)")
    actions: list[str] = Field(description="버튼 라벨 — 클릭 시 message로 회신")


class AuthRequestUi(_UiBase):
    """본인 인증 요청 (mock). 인증 완료 후 '인증완료'를 회신한다."""

    type: Literal["auth_request"]
    methods: list[str]
    actions: list[str]


ChatUi = Annotated[
    Union[
        AccountCardListUi,
        SearchSelectUi,
        NumberInputUi,
        ConfirmModalUi,
        AuthRequestUi,
    ],
    Field(discriminator="type"),
]


class ChatRequest(BaseModel):
    """채팅 요청.

    thread_id: 직전 응답의 status가 waiting_input일 때만 그대로 회송한다.
               (interrupt 재개용. 그 외에는 생략 — 매 턴 새 대화로 처리된다.)
    """

    message: str = Field(min_length=1, max_length=2000, description="사용자 발화")
    thread_id: str | None = Field(None, description="재개할 대화 스레드 id")
    user_id: str = Field("user_001", description="사용자 id (mock 데이터 기준)")


class ChatResponse(BaseModel):
    """채팅 응답.

    status 의미:
      - completed:     워크플로우 정상 완료
      - waiting_input: 추가 입력 대기 (reply가 질문, thread_id 회송 필요)
      - blocked:       가드레일 차단
      - no_match:      매칭되는 워크플로우 없음
      - failed:        워크플로우 실행 실패
    """

    reply: str = Field(description="사용자에게 보여줄 응답 문장")
    status: ChatStatus = Field(description="처리 결과 상태")
    thread_id: str = Field(description="이번 턴의 대화 스레드 id")
    prompt_for: str | None = Field(
        None,
        description=(
            "waiting_input일 때 요청 중인 입력의 state 키. "
            "네임스페이스 키다 (예: balance.account_selection_input). "
            "클라이언트는 opaque 문자열로 취급하면 된다."
        ),
    )
    ui: ChatUi | None = Field(
        None,
        description=(
            "waiting_input일 때 구조화 UI 힌트 (시트 UI Spec 계약). "
            "type으로 판별되는 5종 모델 참조 (AccountCardListUi 등). "
            "없으면 reply 텍스트로 렌더링한다 (폴백)."
        ),
    )
