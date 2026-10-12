"""Tests for searching the catalogue."""

from __future__ import annotations

from datetime import date

import pytest

from library import BookSearch, ValidationError
from library.search import like_pattern

ADULT, STUDENT, CHILD = 1, 2, 3


@pytest.fixture
def shelf(library):
    library.add_book("9780306406157", "Things Fall Apart", "Chinua Achebe", 1958, copies=2)
    library.add_book("080442957X", "Purple Hibiscus", "Chimamanda Ngozi Adichie", 2003)
    library.add_book("9781234567897", "Half of a Yellow Sun", "Chimamanda Ngozi Adichie", 2006)
    library.add_book("9780131103627", "100% Python_Tricks", "A. Coder", 2020)
    library.register_member("adult", "Ronaldo", "ronaldo@example.com")
    library.register_member("student", "Amara", "amara@example.com")
    return library


def titles(books) -> list[str]:
    return [b.title for b in books]


def test_no_filters_returns_everything(shelf):
    assert len(shelf.search()) == 4


def test_text_matches_title_or_author_in_any_case(shelf):
    assert titles(shelf.search("ACHEBE")) == ["Things Fall Apart"]
    assert titles(shelf.search("sun")) == ["Half of a Yellow Sun"]


def test_author_and_title(shelf):
    assert titles(shelf.search(author="adichie")) == ["Half of a Yellow Sun", "Purple Hibiscus"]
    assert titles(shelf.search(author="adichie", title="purple")) == ["Purple Hibiscus"]


def test_year_range(shelf):
    assert titles(shelf.search(year_from=2000, year_to=2010)) == \
        ["Half of a Yellow Sun", "Purple Hibiscus"]
    assert titles(shelf.search(year_to=1960)) == ["Things Fall Apart"]


def test_available_only_skips_books_that_are_all_out(shelf):
    shelf.lend(2, ADULT)  # Purple Hibiscus has one copy
    shelf.lend(1, ADULT)  # Things Fall Apart still has one left
    found = titles(shelf.search(author="chi", available_only=True))
    assert found == ["Half of a Yellow Sun", "Things Fall Apart"]


def test_available_only_skips_copies_kept_for_a_reservation(shelf):
    loan = shelf.lend(2, ADULT)
    shelf.reserve(2, STUDENT)
    shelf.give_back(loan.loan_id)
    assert "Purple Hibiscus" not in titles(shelf.search(available_only=True))


def test_wildcards_are_searched_as_plain_characters(shelf):
    assert titles(shelf.search("100%")) == ["100% Python_Tricks"]
    assert titles(shelf.search("n_T")) == ["100% Python_Tricks"]
    assert shelf.search("%") == shelf.search("100%")


def test_tricky_text_is_safe(shelf):
    assert shelf.search("'; DROP TABLE books; --") == []
    assert len(shelf.books) == 4


def test_blank_text_means_no_filter(shelf):
    assert len(shelf.search("   ")) == 4


def test_like_pattern():
    assert like_pattern("a%b_c\\") == "%a\\%b\\_c\\\\%"


@pytest.mark.parametrize("kwargs", [
    {"text": 5},
    {"year_from": "2000"},
    {"year_to": True},
    {"year_from": 2010, "year_to": 2000},
    {"available_on": "2026-10-01"},
])
def test_bad_searches(kwargs):
    with pytest.raises(ValidationError):
        BookSearch(**kwargs)


def test_search_object_on_its_own():
    query = BookSearch(text="  sun ", available_on=date(2026, 10, 1))
    assert query.text == "sun"
