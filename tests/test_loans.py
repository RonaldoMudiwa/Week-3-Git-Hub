"""Tests for the Loan record and saving loans."""

from __future__ import annotations

from datetime import date

import pytest

from library import (
    AdultMember,
    Book,
    Loan,
    LoanNotFoundError,
    NotFoundError,
    SQLiteBookRepository,
    SQLiteLoanRepository,
    SQLiteMemberRepository,
    ValidationError,
)

OCT_1 = date(2026, 10, 1)
OCT_22 = date(2026, 10, 22)


def make(**changes) -> Loan:
    details = {"book_id": 1, "member_id": 1, "borrowed_on": OCT_1, "due_on": OCT_22}
    details.update(changes)
    return Loan(**details)


class TestLoan:
    def test_new_loan_is_not_returned(self):
        loan = make()
        assert not loan.is_returned
        assert loan.renewals == 0

    def test_overdue_counts_days_after_the_due_date(self):
        loan = make()
        assert not loan.is_overdue(OCT_22)
        assert loan.days_overdue(OCT_22) == 0
        assert loan.is_overdue(date(2026, 10, 25))
        assert loan.days_overdue(date(2026, 10, 25)) == 3

    def test_returned_loan_remembers_how_late_it_was(self):
        loan = make(returned_on=date(2026, 10, 24))
        assert loan.is_returned
        assert not loan.is_overdue(date(2026, 12, 1))
        assert loan.days_overdue(date(2026, 12, 1)) == 2

    def test_returned_early_is_zero_days_late(self):
        assert make(returned_on=date(2026, 10, 5)).days_overdue(date(2026, 11, 30)) == 0

    @pytest.mark.parametrize("changes", [
        {"due_on": date(2026, 9, 30)},
        {"returned_on": date(2026, 9, 30)},
        {"returned_on": "2026-10-05"},
        {"borrowed_on": "2026-10-01"},
        {"book_id": 0},
        {"member_id": "1"},
        {"renewals": -1},
    ])
    def test_bad_values_are_refused(self, changes):
        with pytest.raises(ValidationError):
            make(**changes)

    def test_with_changes(self):
        loan = make()
        assert loan.with_changes(renewals=1).renewals == 1
        assert loan.renewals == 0


@pytest.fixture
def loans(db) -> SQLiteLoanRepository:
    SQLiteBookRepository(db).add(Book("9780306406157", "Things Fall Apart", "Chinua Achebe"))
    SQLiteBookRepository(db).add(Book("080442957X", "Purple Hibiscus", "Chimamanda Adichie"))
    SQLiteMemberRepository(db).add(AdultMember("Ronaldo", "ronaldo@example.com"))
    SQLiteMemberRepository(db).add(AdultMember("Amara", "amara@example.com"))
    return SQLiteLoanRepository(db)


class TestLoanRepository:
    def test_add_and_get(self, loans):
        saved = loans.add(make())
        assert saved.loan_id == 1
        assert loans.get(1) == saved

    def test_saved_loan_cannot_be_added_again(self, loans):
        with pytest.raises(ValidationError):
            loans.add(loans.add(make()))

    def test_unknown_book_or_member_is_refused(self, loans):
        with pytest.raises(NotFoundError):
            loans.add(make(book_id=99))
        with pytest.raises(NotFoundError):
            loans.add(make(member_id=99))

    def test_update_return_and_renewal(self, loans):
        saved = loans.add(make())
        loans.update(saved.with_changes(returned_on=date(2026, 10, 9), renewals=1))
        loaded = loans.get(saved.loan_id)
        assert loaded.returned_on == date(2026, 10, 9)
        assert loaded.renewals == 1

    def test_update_needs_a_saved_loan(self, loans):
        with pytest.raises(ValidationError):
            loans.update(make())
        with pytest.raises(LoanNotFoundError):
            loans.update(make(loan_id=40))

    def test_missing_loan(self, loans):
        with pytest.raises(LoanNotFoundError, match="7"):
            loans.get(7)

    def test_active_and_history(self, loans):
        first = loans.add(make())
        second = loans.add(make(book_id=2, borrowed_on=date(2026, 10, 3), due_on=date(2026, 10, 20)))
        loans.update(first.with_changes(returned_on=date(2026, 10, 8)))
        loans.add(make(member_id=2))

        assert [l.loan_id for l in loans.active_for_member(1)] == [second.loan_id]
        assert [l.loan_id for l in loans.history_for_member(1)] == [second.loan_id, first.loan_id]
        assert len(loans.active_for_book(1)) == 1
        assert loans.count_for_book(1) == 2
        assert [l.due_on for l in loans.all_active()] == [date(2026, 10, 20), OCT_22]
