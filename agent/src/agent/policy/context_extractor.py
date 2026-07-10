"""전역 가드레일 컨텍스트 추출.

global scope 규칙의 expression 변수(action_count, target_owner, action_type)를
state에서 만들어 GuardrailEngine에 넘길 context dict를 구성한다.

target_owner / action_type은 키워드 휴리스틱 MVP다. 가드레일 오탐은 정상 요청
차단으로 이어지므로 '3인칭 소유 표현 + 계좌 단어 인접'처럼 보수적인 패턴만
쓴다. (후속 과제: extract_transfer_slots처럼 LLM 우선 + 키워드 폴백으로 승격)
"""

from __future__ import annotations

import re

# "남편 계좌", "엄마의 통장", "친구 잔액"처럼 3인칭 소유 표현이 계좌 단어와
# 인접한 경우만 타인 계좌 접근으로 본다 ("친구한테 보내줘"는 매칭되지 않음).
_THIRD_PARTY_ACCOUNT = re.compile(
    r"(남편|아내|엄마|아빠|어머니|아버지|부모님|친구|동생|형|누나|언니|오빠"
    r"|타인|다른\s*사람|남)\s*(?:의)?\s*(계좌|통장|잔액|잔고)"
)

_INQUIRY_WORDS = ["잔액", "잔고", "조회", "얼마", "알려줘", "확인해", "보여줘"]


def build_global_context(state: dict) -> dict:
    """global 규칙 평가용 context를 만든다.

    누락 변수는 규칙 미발동으로 처리되므로(엔진의 보수적 기본값),
    확신할 수 있는 신호만 context에 넣는다.
    """
    user_input = str(state.get("user_input") or "")
    context: dict = {
        "user_input": user_input,
        # 같은 thread에서 누적된 스텝 실행 수 (tool_abuse_block용)
        "action_count": len(state.get("execution_trace") or []),
    }
    if _THIRD_PARTY_ACCOUNT.search(user_input):
        context["target_owner"] = "other"
    if any(word in user_input for word in _INQUIRY_WORDS):
        context["action_type"] = "inquiry"
    return context
