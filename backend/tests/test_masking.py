"""계좌번호 마스킹 유틸 검증(PII 규칙)."""

from backend.utils.masking import mask_account_number


def test_masks_middle_group_of_hyphenated():
    assert mask_account_number("3333-12-1234567") == "3333-**-1234567"


def test_masks_all_middle_groups():
    assert mask_account_number("110-222-123456") == "110-***-123456"


def test_two_groups_masks_tail_group():
    assert mask_account_number("1002-1234567") == "1002-*******"


def test_no_hyphen_keeps_head_and_tail():
    assert mask_account_number("3333121234567") == "333******4567"


def test_short_number_fully_masked():
    assert mask_account_number("123456") == "******"


def test_empty_is_empty():
    assert mask_account_number("") == ""
    assert mask_account_number(None) == ""
