"""잔액 조회(wf_balance_inquiry) tool 단위 테스트.

그래프 없이 함수를 직접 호출한다. conftest가 로컬 원장 + API 키 제거를 보장한다.
계좌 선택 키워드 폴백은 키 없는 개발/데모/CI에서 매번 도는 경로라 여기서 고정한다.
"""

from __future__ import annotations

from agent.tools.bank_tools import _parse_account_selection_by_keyword


def test_account_selection_keyword_fallback():
    assert _parse_account_selection_by_keyword("1번", 2) == [1]
    assert _parse_account_selection_by_keyword("1", 2) == [1]
    assert _parse_account_selection_by_keyword("1번이랑 2번", 2) == [1, 2]
    assert _parse_account_selection_by_keyword("둘 다", 2) == [1, 2]
    assert _parse_account_selection_by_keyword("전부", 2) == [1, 2]
    assert _parse_account_selection_by_keyword("아무말", 2) == []  # 범위 밖/없음
    assert _parse_account_selection_by_keyword("9번", 2) == []  # 후보 수 초과
