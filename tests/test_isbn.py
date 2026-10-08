"""Tests for ISBN checking."""

from __future__ import annotations

import pytest

from library import ValidationError, normalise_isbn


@pytest.mark.parametrize("text, expected", [
    ("9780306406157", "9780306406157"),
    ("978-0-306-40615-7", "9780306406157"),
    ("978 0 306 40615 7", "9780306406157"),
    ("0306406152", "9780306406157"),      # the same book as a 10 digit ISBN
    ("0-306-40615-2", "9780306406157"),
    ("080442957X", "9780804429573"),      # X means 10
    ("080442957x", "9780804429573"),
])
def test_valid_isbns(text, expected):
    assert normalise_isbn(text) == expected


@pytest.mark.parametrize("text", [
    "9780306406158",   # wrong check digit
    "0306406153",
    "97803064061",     # too short
    "97803064061577",  # too long
    "978030640615X",   # X only allowed in 10 digit ones
    "X306406152",
    "abcdefghij",
    "",
])
def test_invalid_isbns(text):
    with pytest.raises(ValidationError):
        normalise_isbn(text)


def test_isbn_must_be_text():
    with pytest.raises(ValidationError, match="text"):
        normalise_isbn(9780306406157)
