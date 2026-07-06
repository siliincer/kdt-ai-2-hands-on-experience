"""에이전트 채팅 API 요청/응답 스키마.

에이전트는 내부 서비스이므로 plain JSON을 반환한다.
backend 게이트웨이가 이 응답을 CommonResponse(success/message/data)로 감싼다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChatStatus = Literal["completed", "waiting_input", "blocked", "no_match", "failed"]


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
    ui: dict | None = Field(
        None,
        description=(
            "waiting_input일 때 구조화 UI 힌트 (시트 UI Spec 계약). "
            '{"type": "account_card_list" | "search_select" | "number_input" '
            '| "confirm_modal" | "auth_request", "display"?, "options"?, '
            '"actions"?}. 없으면 reply 텍스트로 렌더링한다 (폴백).'
        ),
    )
