"""계좌번호·예금주명 마스킹 유틸 검증(PII 규칙)."""

from backend.utils.masking import mask_account_number, mask_person_name


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


def test_person_name_three_chars():
    assert mask_person_name("홍길동") == "홍*동"


def test_person_name_four_chars():
    assert mask_person_name("남궁민수") == "남**수"


def test_person_name_two_chars():
    assert mask_person_name("홍길") == "홍*"


def test_person_name_single_char_kept():
    assert mask_person_name("홍") == "홍"


def test_person_name_empty():
    assert mask_person_name("") == ""
    assert mask_person_name(None) == ""
