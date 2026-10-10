"""Tests for lending, returning and renewing through the Library."""

from __future__ import annotations

from datetime import date

import pytest

from library import (
    AlreadyBorrowedError,
    AlreadyReturnedError,
    BookInUseError,
    BookNotFoundError,
    DuplicateError,
    Library,
    LoanError,
    LoanLimitError,
    MemberNotActiveError,
    MemberNotFoundError,
    NoCopiesAvailableError,
    OverdueLoansError,
    RenewalError,
    StudentMember,
    ValidationError,
)

from .conftest import ACHEBE_ISBN

ADULT, STUDENT, CHILD = 1, 2, 3
ACHEBE, ADICHIE = 1, 2


def add_books(library, how_many: int) -> list[int]:
    """Add plain books with made up but valid ISBNs. Returns their ids."""
    ids = []
    for n in range(how_many):
        first_twelve = f"978000000{n:03d}"
        total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first_twelve))
        isbn = first_twelve + str((10 - total % 10) % 10)
        ids.append(library.add_book(isbn, f"Book {n}", "Author").book_id)
    return ids


class TestBooksAndMembers:
    def test_add_and_find_books(self, stocked):
        assert stocked.find_book("0-306-40615-2").title == "Things Fall Apart"
        assert [b.title for b in stocked.books] == ["Purple Hibiscus", "Things Fall Apart"]
        with pytest.raises(BookNotFoundError):
            stocked.find_book("9781234567897")

    def test_same_book_twice(self, stocked):
        with pytest.raises(DuplicateError):
            stocked.add_book(ACHEBE_ISBN, "Again", "Someone")

    def test_register_member_uses_todays_date_and_type(self, stocked, clock):
        member = stocked.get_member(STUDENT)
        assert isinstance(member, StudentMember)
        assert member.joined_on == clock.today
        assert len(stocked.members) == 3

    def test_unknown_member_type(self, library):
        with pytest.raises(ValidationError):
            library.register_member("alien", "Zork", "zork@example.com")

    def test_suspend_and_reinstate_are_saved(self, stocked):
        stocked.suspend_member(ADULT)
        assert not stocked.get_member(ADULT).is_active
        stocked.reinstate_member(ADULT)
        assert stocked.get_member(ADULT).is_active


class TestLending:
    def test_lend_sets_the_due_date_for_the_member_type(self, stocked, clock):
        adult = stocked.lend(ACHEBE, ADULT)
        child = stocked.lend(ACHEBE, CHILD)
        assert adult.borrowed_on == clock.today
        assert adult.due_on == date(2026, 10, 22)
        assert child.due_on == date(2026, 10, 15)

    def test_available_copies_go_down_and_up(self, stocked):
        assert stocked.available_copies(ACHEBE) == 2
        loan = stocked.lend(ACHEBE, ADULT)
        assert stocked.available_copies(ACHEBE) == 1
        stocked.give_back(loan.loan_id)
        assert stocked.available_copies(ACHEBE) == 2

    def test_no_copies_left(self, stocked):
        stocked.lend(ADICHIE, ADULT)
        with pytest.raises(NoCopiesAvailableError, match="Purple Hibiscus"):
            stocked.lend(ADICHIE, STUDENT)

    def test_same_book_twice_to_one_member(self, stocked):
        stocked.lend(ACHEBE, ADULT)
        with pytest.raises(AlreadyBorrowedError):
            stocked.lend(ACHEBE, ADULT)

    def test_loan_limit_depends_on_member_type(self, stocked):
        ids = add_books(stocked, 4)
        for book_id in ids[:3]:
            stocked.lend(book_id, CHILD)
        with pytest.raises(LoanLimitError, match="child"):
            stocked.lend(ids[3], CHILD)
        stocked.lend(ids[3], ADULT)  # an adult can still have it

    def test_suspended_member_cannot_borrow(self, stocked):
        stocked.suspend_member(ADULT)
        with pytest.raises(MemberNotActiveError):
            stocked.lend(ACHEBE, ADULT)

    def test_late_book_blocks_new_loans(self, stocked, clock):
        stocked.lend(ACHEBE, CHILD)
        clock.advance(15)
        with pytest.raises(OverdueLoansError, match="1 late"):
            stocked.lend(ADICHIE, CHILD)

    def test_unknown_book_or_member(self, stocked):
        with pytest.raises(BookNotFoundError):
            stocked.lend(99, ADULT)
        with pytest.raises(MemberNotFoundError):
            stocked.lend(ACHEBE, 99)

    def test_every_lending_refusal_is_a_loan_error(self, stocked):
        stocked.lend(ADICHIE, ADULT)
        for attempt in (lambda: stocked.lend(ADICHIE, STUDENT),
                        lambda: stocked.lend(ADICHIE, ADULT)):
            with pytest.raises(LoanError):
                attempt()

    def test_failed_lend_saves_nothing(self, stocked):
        stocked.lend(ADICHIE, ADULT)
        with pytest.raises(NoCopiesAvailableError):
            stocked.lend(ADICHIE, STUDENT)
        assert stocked.loans_for(STUDENT) == []


class TestReturning:
    def test_give_back_records_the_date(self, stocked, clock):
        loan = stocked.lend(ACHEBE, ADULT)
        clock.advance(5)
        returned = stocked.give_back(loan.loan_id)
        assert returned.returned_on == date(2026, 10, 6)
        assert stocked.loans_for(ADULT) == []
        assert stocked.history_for(ADULT) == [returned]

    def test_cannot_return_twice(self, stocked):
        loan = stocked.lend(ACHEBE, ADULT)
        stocked.give_back(loan.loan_id)
        with pytest.raises(AlreadyReturnedError):
            stocked.give_back(loan.loan_id)

    def test_late_return_lets_them_borrow_again(self, stocked, clock):
        loan = stocked.lend(ACHEBE, CHILD)
        clock.advance(20)
        assert stocked.give_back(loan.loan_id).days_overdue(clock.today) == 6
        stocked.lend(ADICHIE, CHILD)


class TestRenewing:
    def test_renew_counts_from_today(self, stocked, clock):
        loan = stocked.lend(ACHEBE, ADULT)
        clock.advance(10)
        renewed = stocked.renew(loan.loan_id)
        assert renewed.due_on == date(2026, 11, 1)
        assert renewed.renewals == 1
        assert stocked.get_loan(loan.loan_id) == renewed

    def test_renewal_limit_depends_on_member_type(self, stocked):
        adult = stocked.lend(ACHEBE, ADULT)
        child = stocked.lend(ADICHIE, CHILD)
        stocked.renew(adult.loan_id)
        stocked.renew(adult.loan_id)
        stocked.renew(child.loan_id)
        with pytest.raises(RenewalError, match="adult"):
            stocked.renew(adult.loan_id)
        with pytest.raises(RenewalError, match="child"):
            stocked.renew(child.loan_id)

    def test_late_book_cannot_be_renewed(self, stocked, clock):
        loan = stocked.lend(ACHEBE, ADULT)
        clock.advance(22)
        with pytest.raises(RenewalError, match="late"):
            stocked.renew(loan.loan_id)

    def test_returned_book_cannot_be_renewed(self, stocked):
        loan = stocked.lend(ACHEBE, ADULT)
        stocked.give_back(loan.loan_id)
        with pytest.raises(RenewalError):
            stocked.renew(loan.loan_id)


class TestCopiesAndRemoving:
    def test_buy_more_copies(self, stocked):
        assert stocked.set_copies(ADICHIE, 3).copies == 3
        assert stocked.available_copies(ADICHIE) == 3

    def test_cannot_own_fewer_than_are_out(self, stocked):
        stocked.lend(ACHEBE, ADULT)
        stocked.lend(ACHEBE, STUDENT)
        with pytest.raises(BookInUseError):
            stocked.set_copies(ACHEBE, 1)
        assert stocked.get_book(ACHEBE).copies == 2

    def test_remove_a_book_never_lent(self, stocked):
        stocked.remove_book(ADICHIE)
        with pytest.raises(BookNotFoundError):
            stocked.get_book(ADICHIE)

    def test_book_with_history_cannot_be_removed(self, stocked):
        stocked.give_back(stocked.lend(ACHEBE, ADULT).loan_id)
        with pytest.raises(BookInUseError, match="history"):
            stocked.remove_book(ACHEBE)


def test_active_loans_soonest_due_first(stocked):
    stocked.lend(ACHEBE, ADULT)
    stocked.lend(ADICHIE, CHILD)
    assert [l.member_id for l in stocked.active_loans] == [CHILD, ADULT]


def test_loans_for_unknown_member(stocked):
    with pytest.raises(MemberNotFoundError):
        stocked.loans_for(99)
    with pytest.raises(MemberNotFoundError):
        stocked.history_for(99)


def test_today_uses_the_clock(library, clock):
    assert library.today == clock.today


def test_default_clock_is_the_real_date(db):
    assert Library.open(db).today == date.today()
