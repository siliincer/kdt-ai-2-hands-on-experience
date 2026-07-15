"""merge_data reducer 검증."""

from __future__ import annotations

from agent.state import merge_data


def test_both_none_returns_empty_dict():
    assert merge_data(None, None) == {}


def test_none_left_copies_right():
    right = {"balance.account_hint": "생활비"}
    result = merge_data(None, right)
    assert result == right
    assert result is not right  # 복사본이어야 한다


def test_none_right_copies_left():
    left = {"balance.account_hint": "생활비"}
    result = merge_data(left, None)
    assert result == left
    assert result is not left


def test_right_wins_on_conflict():
    left = {"balance.account_hint": "생활비", "transfer.amount": 1000}
    right = {"balance.account_hint": "입출금"}
    result = merge_data(left, right)
    assert result["balance.account_hint"] == "입출금"
    assert result["transfer.amount"] == 1000


def test_inputs_not_mutated():
    left = {"a": 1}
    right = {"b": 2}
    merge_data(left, right)
    assert left == {"a": 1}
    assert right == {"b": 2}
