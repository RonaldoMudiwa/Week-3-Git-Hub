"""Tests for saving and finding books and members in SQLite."""

from __future__ import annotations

from datetime import date

import pytest

from library import (
    AdultMember,
    Book,
    BookNotFoundError,
    ChildMember,
    DuplicateError,
    MemberNotFoundError,
    MemberStatus,
    SQLiteBookRepository,
    SQLiteMemberRepository,
    StudentMember,
    ValidationError,
)

ACHEBE = "9780306406157"
ADICHIE = "080442957X"


@pytest.fixture
def books(db) -> SQLiteBookRepository:
    return SQLiteBookRepository(db)


@pytest.fixture
def members(db) -> SQLiteMemberRepository:
    return SQLiteMemberRepository(db)


def achebe() -> Book:
    return Book(ACHEBE, "Things Fall Apart", "Chinua Achebe", 1958, copies=2)


class TestBooks:
    def test_add_gives_an_id_and_get_finds_it(self, books):
        saved = books.add(achebe())
        assert saved.book_id == 1
        assert books.get(1) == saved

    def test_find_by_isbn_in_any_format(self, books):
        saved = books.add(achebe())
        assert books.find_by_isbn("0-306-40615-2") == saved
        assert books.find_by_isbn(ADICHIE) is None

    def test_same_isbn_twice_is_refused(self, books):
        books.add(achebe())
        with pytest.raises(DuplicateError, match=ACHEBE):
            books.add(Book("0306406152", "Copy", "Someone"))

    def test_saved_book_cannot_be_added_again(self, books):
        saved = books.add(achebe())
        with pytest.raises(ValidationError):
            books.add(saved)

    def test_update(self, books):
        saved = books.add(achebe())
        books.update(saved.with_changes(copies=4, title="Things Fall Apart (new edition)"))
        assert books.get(saved.book_id).copies == 4

    def test_update_to_an_isbn_already_used(self, books):
        books.add(achebe())
        other = books.add(Book(ADICHIE, "Purple Hibiscus", "Chimamanda Adichie"))
        with pytest.raises(DuplicateError):
            books.update(other.with_changes(isbn=ACHEBE))

    def test_update_needs_a_saved_book(self, books):
        with pytest.raises(ValidationError):
            books.update(achebe())
        with pytest.raises(BookNotFoundError):
            books.update(achebe().with_changes(book_id=99))

    def test_remove(self, books):
        saved = books.add(achebe())
        books.remove(saved.book_id)
        assert books.all() == []
        with pytest.raises(BookNotFoundError):
            books.remove(saved.book_id)

    def test_missing_book(self, books):
        with pytest.raises(BookNotFoundError, match="99"):
            books.get(99)

    def test_all_sorted_by_title_ignoring_case(self, books):
        books.add(Book(ADICHIE, "purple Hibiscus", "Chimamanda Adichie"))
        books.add(achebe())
        assert [b.title for b in books.all()] == ["purple Hibiscus", "Things Fall Apart"]

    def test_tricky_text_is_stored_safely(self, books):
        title = "Bobby'); DROP TABLE books; --"
        saved = books.add(Book(ACHEBE, title, "O'Brien"))
        assert books.get(saved.book_id).title == title
        assert books.get(saved.book_id).author == "O'Brien"


class TestMembers:
    def test_add_and_get_keeps_the_member_type(self, members):
        added = members.add(StudentMember("Amara Okafor", "amara@example.com",
                                          joined_on=date(2026, 9, 1)))
        assert added.member_id == 1
        loaded = members.get(1)
        assert isinstance(loaded, StudentMember)
        assert loaded.max_loans == 8
        assert loaded.joined_on == date(2026, 9, 1)
        assert loaded.status is MemberStatus.ACTIVE

    def test_same_email_twice_is_refused(self, members):
        members.add(AdultMember("Ronaldo", "ronaldo@example.com"))
        with pytest.raises(DuplicateError, match="ronaldo@example.com"):
            members.add(ChildMember("Ron", "RONALDO@example.com"))

    def test_saved_member_cannot_be_added_again(self, members):
        member = members.add(AdultMember("Ronaldo", "ronaldo@example.com"))
        with pytest.raises(ValidationError):
            members.add(member)

    def test_find_by_email(self, members):
        members.add(AdultMember("Ronaldo", "ronaldo@example.com"))
        assert members.find_by_email(" Ronaldo@Example.com ").name == "Ronaldo"
        assert members.find_by_email("nobody@example.com") is None

    def test_update_saves_status_and_details(self, members):
        member = members.add(AdultMember("Ronaldo", "ronaldo@example.com"))
        member.suspend()
        member.name = "Ronaldo Mudiwa"
        members.update(member)
        loaded = members.get(member.member_id)
        assert loaded.status is MemberStatus.SUSPENDED
        assert loaded.name == "Ronaldo Mudiwa"

    def test_update_to_an_email_already_used(self, members):
        members.add(AdultMember("Ronaldo", "ronaldo@example.com"))
        amara = members.add(AdultMember("Amara", "amara@example.com"))
        amara.email = "ronaldo@example.com"
        with pytest.raises(DuplicateError):
            members.update(amara)

    def test_update_needs_a_saved_member(self, members):
        with pytest.raises(ValidationError):
            members.update(AdultMember("Ronaldo", "ronaldo@example.com"))
        with pytest.raises(MemberNotFoundError):
            members.update(AdultMember("Ronaldo", "ronaldo@example.com", member_id=50))

    def test_missing_member(self, members):
        with pytest.raises(MemberNotFoundError, match="42"):
            members.get(42)

    def test_all_in_joining_order(self, members):
        members.add(ChildMember("Zara", "zara@example.com"))
        members.add(AdultMember("Ade", "ade@example.com"))
        assert [m.name for m in members.all()] == ["Zara", "Ade"]
