"""민감정보 마스킹 공통 유틸.

Agent Tool API 는 전체 계좌번호를 응답·State·로그에 노출하지 않는다(계약 2·25장).
계좌번호는 앞 그룹과 마지막 그룹만 남기고 가운데를 가린다.
"""

from __future__ import annotations

_MIN_GROUPS_TO_MASK = 3
_HEAD_KEEP = 3
_TAIL_KEEP = 4


def mask_account_number(number: str | None) -> str:
    """계좌번호 가운데를 마스킹한다.

    - 하이픈 구분(예: "3333-12-1234567"): 가운데 그룹을 자릿수만큼 * 로 가린다
      → "3333-**-1234567".
    - 하이픈 미포함(예: "3333121234567"): 앞 3자리·뒤 4자리만 남기고 가린다.
    - 그룹이 2개 이하이거나 값이 없으면 안전하게 처리한다.
    """
    if not number:
        return ""

    if "-" in number:
        groups = number.split("-")
        if len(groups) >= _MIN_GROUPS_TO_MASK:
            masked_mid = ["*" * len(g) for g in groups[1:-1]]
            return "-".join([groups[0], *masked_mid, groups[-1]])
        # 그룹 2개: 가운데가 없으니 뒤 그룹만 자릿수 마스킹
        return "-".join([groups[0], "*" * len(groups[-1])])

    if len(number) <= _HEAD_KEEP + _TAIL_KEEP:
        return "*" * len(number)
    head = number[:_HEAD_KEEP]
    tail = number[-_TAIL_KEEP:]
    return f"{head}{'*' * (len(number) - _HEAD_KEEP - _TAIL_KEEP)}{tail}"


def mask_person_name(name: str | None) -> str:
    """예금주명 마스킹: 첫 글자와 마지막 글자만 남긴다(계약 14.4 예시 "홍*동").

    - 3자 이상: 가운데를 * 로 ("홍길동" → "홍*동", "남궁민수" → "남**수")
    - 2자: 뒷글자를 * 로 ("홍길" → "홍*")
    - 1자 이하·없음: 그대로/빈 문자열(마스킹할 가운데가 없음)
    """
    if not name:
        return ""
    trimmed = name.strip()
    if len(trimmed) <= 1:
        return trimmed
    if len(trimmed) == 2:
        return f"{trimmed[0]}*"
    return f"{trimmed[0]}{'*' * (len(trimmed) - 2)}{trimmed[-1]}"
