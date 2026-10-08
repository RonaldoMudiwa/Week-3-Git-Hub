"""Tests for Book."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from library import Book, ValidationError

ISBN = "9780306406157"


def make(**changes) -> Book:
    details = {"isbn": ISBN, "title": "Things Fall Apart", "author": "Chinua Achebe",
               "year": 1958, "copies": 2}
    details.update(changes)
    return Book(**details)


def test_details_are_kept():
    book = make()
    assert book.title == "Things Fall Apart"
    assert book.author == "Chinua Achebe"
    assert book.year == 1958
    assert book.copies == 2
    assert book.book_id is None


def test_text_is_tidied_and_isbn_made_13_digits():
    book = make(title="  Things Fall Apart ", isbn="0-306-40615-2")
    assert book.title == "Things Fall Apart"
    assert book.isbn == ISBN


def test_year_is_optional():
    assert make(year=None).year is None
    assert str(make(year=None)) == "Things Fall Apart by Chinua Achebe"


def test_str():
    assert str(make()) == "Things Fall Apart by Chinua Achebe, 1958"


@pytest.mark.parametrize("changes", [
    {"title": ""},
    {"title": "   "},
    {"author": None},
    {"isbn": "123"},
    {"copies": 0},
    {"copies": -1},
    {"copies": 1.5},
    {"copies": True},
    {"year": 1200},
    {"year": 3000},
    {"year": "1958"},
    {"book_id": 0},
])
def test_bad_values_are_refused(changes):
    with pytest.raises(ValidationError):
        make(**changes)


def test_cannot_be_changed_in_place():
    with pytest.raises(FrozenInstanceError):
        make().title = "Other"


def test_with_changes_makes_a_new_checked_copy():
    book = make()
    more = book.with_changes(copies=5)
    assert more.copies == 5
    assert book.copies == 2
    with pytest.raises(ValidationError):
        book.with_changes(copies=0)


def test_books_with_the_same_details_are_equal():
    assert make() == make()
    assert make() != make(copies=3)
