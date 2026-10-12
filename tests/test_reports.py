"""Tests for the librarian's reports and the text tables."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from library import Book, Fine, LibraryReport, Loan, Reservation, ReservationStatus, TextFormatter
from library.reports import MemberRow, OverdueRow, PopularRow, StockSummary

D = Decimal
ADULT, STUDENT, CHILD = 1, 2, 3
ACHEBE, ADICHIE = 1, 2


@pytest.fixture
def report(db, clock) -> LibraryReport:
    return LibraryReport(db, clock)


@pytest.fixture
def busy(stocked, clock):
    """Some history: returned loans, a late book, a fine and a reservation."""
    first = stocked.lend(ACHEBE, ADULT)
    clock.advance(25)
    stocked.give_back(first.loan_id)                # 4 days late: £1.00 fine
    stocked.lend(ACHEBE, STUDENT)
    stocked.lend(ADICHIE, CHILD)                    # due in 14 days
    stocked.reserve(ADICHIE, ADULT)
    clock.advance(20)                               # the child's book is now 6 days late
    return stocked


class TestReport:
    def test_overdue(self, busy, report):
        rows = report.overdue()
        assert [(r.title, r.member_name, r.days_late) for r in rows] == \
            [("Purple Hibiscus", "Tendai Moyo", 6)]

    def test_most_borrowed(self, busy, report):
        rows = report.most_borrowed()
        assert rows[0] == PopularRow("Things Fall Apart", "Chinua Achebe", 2)
        assert rows[1].times_borrowed == 1
        assert len(report.most_borrowed(limit=1)) == 1

    def test_members(self, busy, report):
        rows = {r.member_id: r for r in report.members()}
        assert rows[ADULT].books_on_loan == 0
        assert rows[ADULT].owed == D("1.00")
        assert rows[STUDENT].books_on_loan == 1
        assert rows[CHILD].member_type == "child"
        assert report.total_owed() == D("1.00")

    def test_stock(self, busy, report):
        stock = report.stock()
        assert (stock.titles, stock.copies, stock.on_loan) == (2, 3, 2)
        assert stock.on_shelf == 1

    def test_kept_copies_are_counted(self, busy, report):
        busy.give_back(busy.loans_for(CHILD)[0].loan_id)
        assert report.stock().kept_for_reservations == 1
        assert report.stock().on_shelf == 1

    def test_empty_library(self, report):
        assert report.overdue() == []
        assert report.most_borrowed() == []
        assert report.members() == []
        assert report.stock() == StockSummary(0, 0, 0, 0)
        assert report.total_owed() == D("0.00")


class TestFormatter:
    fmt = TextFormatter()

    def test_books(self):
        books = [Book("9780306406157", "Things Fall Apart", "Chinua Achebe", 1958, 2, book_id=1)]
        assert "Things Fall Apart" in self.fmt.books(books)
        assert "1/2" in self.fmt.books(books, {1: 1})
        assert self.fmt.books([]) == "No books found."

    def test_long_titles_are_cut(self):
        book = Book("9780306406157", "A" * 60, "B", book_id=1)
        line = self.fmt.books([book]).splitlines()[2]
        assert "A" * 30 + "..." in line
        assert "A" * 34 not in line

    def test_members(self):
        rows = [MemberRow(1, "Ronaldo", "adult", "active", 2, D("1.5"))]
        assert "£1.50" in self.fmt.members(rows)
        assert self.fmt.members([]) == "No members yet."

    def test_loans_show_late_ones(self):
        loans = [Loan(1, 1, date(2026, 10, 1), date(2026, 10, 5), loan_id=3)]
        text = self.fmt.loans(loans, {1: "Things Fall Apart"}, date(2026, 10, 8))
        assert "3 days late" in text
        assert "late" not in self.fmt.loans(loans, {1: "X"}, date(2026, 10, 2))
        assert self.fmt.loans([], {}, date(2026, 10, 1)) == "No books on loan."

    def test_reservations(self):
        rows = [Reservation(1, 1, date(2026, 10, 1), ReservationStatus.READY,
                            date(2026, 10, 4), reservation_id=2)]
        assert "2026-10-04" in self.fmt.reservations(rows, {1: "Purple Hibiscus"})
        assert self.fmt.reservations([], {}) == "No reservations."

    def test_fines(self):
        fines = [Fine(1, 1, "2", date(2026, 10, 1), fine_id=1),
                 Fine(2, 1, "1", date(2026, 10, 1), date(2026, 10, 2), fine_id=2)]
        text = self.fmt.fines(fines)
        assert "not yet" in text and "2026-10-02" in text
        assert self.fmt.fines([]) == "No fines."

    def test_overdue_and_popular(self):
        overdue = [OverdueRow(1, "Purple Hibiscus", "Tendai", "t@example.com",
                              date(2026, 10, 1), 6)]
        assert "6 d" in self.fmt.overdue(overdue)
        assert self.fmt.overdue([]) == "Nothing is overdue."
        assert "Achebe" in self.fmt.popular([PopularRow("Things", "Achebe", 3)])
        assert self.fmt.popular([]) == "Nothing has been borrowed yet."

    def test_stock(self):
        text = self.fmt.stock(StockSummary(2, 5, 2, 1))
        assert text.splitlines()[-1].split()[-1] == "2"
