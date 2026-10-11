"""Tests for late fines: the rules, the records, and how the Library uses them."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from library import (
    DailyFine,
    Fine,
    FineError,
    FineNotFoundError,
    FinesOwedError,
    Library,
    NoFine,
    SQLiteFineRepository,
    ValidationError,
    format_money,
    to_money,
)

D = Decimal
ADULT, STUDENT, CHILD = 1, 2, 3
ACHEBE, ADICHIE = 1, 2


class TestPolicies:
    def test_daily_fine_adds_up_by_the_day(self):
        policy = DailyFine("0.25", maximum="10")
        assert policy.fine_for(0) == D("0.00")
        assert policy.fine_for(1) == D("0.25")
        assert policy.fine_for(7) == D("1.75")

    def test_daily_fine_stops_at_the_maximum(self):
        assert DailyFine("0.25", maximum="10").fine_for(400) == D("10.00")

    def test_no_fine(self):
        assert NoFine().fine_for(100) == D("0.00")

    @pytest.mark.parametrize("per_day, maximum", [("0", "10"), ("0.25", "0"), ("-1", "5")])
    def test_amounts_must_be_above_zero(self, per_day, maximum):
        with pytest.raises(ValidationError):
            DailyFine(per_day, maximum)

    def test_days_must_be_a_whole_number(self):
        with pytest.raises(ValidationError):
            DailyFine("0.25", "10").fine_for(-1)

    def test_reprs(self):
        assert repr(NoFine()) == "NoFine()"
        policy = DailyFine("0.25", maximum="10")
        assert repr(policy) == "DailyFine('0.25', maximum='10.00')"
        assert (policy.per_day, policy.maximum) == (D("0.25"), D("10.00"))


class TestFine:
    def test_details(self):
        fine = Fine(1, 1, "1.5", date(2026, 10, 9))
        assert fine.amount == D("1.50")
        assert not fine.is_paid
        assert str(fine) == "£1.50 for loan 1 (unpaid)"
        paid = fine.with_changes(paid_on=date(2026, 10, 10))
        assert str(paid) == "£1.50 for loan 1 (paid 2026-10-10)"

    @pytest.mark.parametrize("kwargs", [
        {"amount": "0"},
        {"amount": "-1"},
        {"charged_on": "2026-10-09"},
        {"paid_on": date(2026, 10, 1)},
    ])
    def test_bad_values(self, kwargs):
        details = {"loan_id": 1, "member_id": 1, "amount": "1", "charged_on": date(2026, 10, 9)}
        details.update(kwargs)
        with pytest.raises(ValidationError):
            Fine(**details)


class TestMoney:
    def test_to_money(self):
        assert to_money("1.005") == D("1.01")
        assert to_money(3) == D("3.00")

    @pytest.mark.parametrize("value", [1.5, True, None, "abc", "inf"])
    def test_bad_money(self, value):
        with pytest.raises(ValidationError):
            to_money(value)

    def test_format(self):
        assert format_money(D("1234.5")) == "£1,234.50"
        assert format_money(D("-2")) == "-£2.00"


def return_late(library, clock, book_id, member_id, days_late):
    """Lend a book, wait until it's this many days late, then return it."""
    loan = library.lend(book_id, member_id)
    clock.advance((loan.due_on - clock.today).days + days_late)
    return library.give_back(loan.loan_id)


class TestLibraryFines:
    def test_on_time_return_has_no_fine(self, stocked, clock):
        loan = stocked.lend(ACHEBE, ADULT)
        clock.advance(21)
        receipt = stocked.give_back(loan.loan_id)
        assert receipt.fine is None
        assert stocked.amount_owed(ADULT) == D("0.00")

    def test_late_return_charges_by_member_type(self, stocked, clock):
        adult = return_late(stocked, clock, ACHEBE, ADULT, 4)
        assert adult.fine.amount == D("1.00")
        student = return_late(stocked, clock, ACHEBE, STUDENT, 4)
        assert student.fine.amount == D("0.60")
        child = return_late(stocked, clock, ACHEBE, CHILD, 4)
        assert child.fine is None

    def test_fines_are_saved(self, stocked, clock):
        receipt = return_late(stocked, clock, ACHEBE, ADULT, 2)
        assert stocked.fines_for(ADULT) == [receipt.fine]
        assert stocked.unpaid_fines == [receipt.fine]
        assert receipt.fine.charged_on == clock.today

    def test_paying_a_fine(self, stocked, clock):
        fine = return_late(stocked, clock, ACHEBE, ADULT, 2).fine
        paid = stocked.pay_fine(fine.fine_id)
        assert paid.paid_on == clock.today
        assert stocked.amount_owed(ADULT) == D("0.00")
        assert stocked.fines_for(ADULT, unpaid_only=True) == []
        assert stocked.fines_for(ADULT) == [paid]
        with pytest.raises(FineError):
            stocked.pay_fine(fine.fine_id)

    def test_big_fines_stop_borrowing_until_paid(self, stocked, clock):
        fine = return_late(stocked, clock, ACHEBE, ADULT, 20).fine   # £5.00
        with pytest.raises(FinesOwedError, match="£5.00"):
            stocked.lend(ADICHIE, ADULT)
        stocked.pay_fine(fine.fine_id)
        stocked.lend(ADICHIE, ADULT)

    def test_small_fines_dont_stop_borrowing(self, stocked, clock):
        return_late(stocked, clock, ACHEBE, ADULT, 3)
        stocked.lend(ADICHIE, ADULT)

    def test_fine_limit_can_be_changed(self, db, clock):
        library = Library.open(db, clock, fine_limit="0.50")
        library.add_book("9780306406157", "Things Fall Apart", "Chinua Achebe")
        library.add_book("080442957X", "Purple Hibiscus", "Chimamanda Adichie")
        library.register_member("adult", "Ronaldo", "ronaldo@example.com")
        return_late(library, clock, 1, 1, 2)
        with pytest.raises(FinesOwedError):
            library.lend(2, 1)

    def test_missing_fine(self, stocked):
        with pytest.raises(FineNotFoundError):
            stocked.pay_fine(5)


class TestFineRepository:
    def test_one_fine_per_loan(self, stocked, clock, db):
        fine = return_late(stocked, clock, ACHEBE, ADULT, 2).fine
        repo = SQLiteFineRepository(db)
        with pytest.raises(ValidationError, match="already has a fine"):
            repo.add(Fine(fine.loan_id, ADULT, "1", clock.today))

    def test_saved_fine_cannot_be_added_again(self, stocked, clock, db):
        fine = return_late(stocked, clock, ACHEBE, ADULT, 2).fine
        with pytest.raises(ValidationError):
            SQLiteFineRepository(db).add(fine)

    def test_update_needs_a_saved_fine(self, db, clock):
        repo = SQLiteFineRepository(db)
        with pytest.raises(ValidationError):
            repo.update(Fine(1, 1, "1", clock.today))
        with pytest.raises(FineNotFoundError):
            repo.update(Fine(1, 1, "1", clock.today, fine_id=9))
