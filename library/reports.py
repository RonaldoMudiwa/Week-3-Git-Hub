"""Reports for the librarian, and turning them into text.

LibraryReport asks the database questions and returns plain rows.
TextFormatter turns rows into tables for the terminal. Keeping the two
apart means the same numbers could go into a web page later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Sequence

from .book import Book
from .database import Database
from .fines import Fine
from .loans import Loan
from .members import Member
from .money import ZERO, format_money
from .reservations import Reservation


@dataclass(frozen=True)
class OverdueRow:
    loan_id: int
    title: str
    member_name: str
    email: str
    due_on: date
    days_late: int


@dataclass(frozen=True)
class PopularRow:
    title: str
    author: str
    times_borrowed: int


@dataclass(frozen=True)
class MemberRow:
    member_id: int
    name: str
    member_type: str
    status: str
    books_on_loan: int
    owed: Decimal


@dataclass(frozen=True)
class StockSummary:
    titles: int
    copies: int
    on_loan: int
    kept_for_reservations: int

    @property
    def on_shelf(self) -> int:
        return self.copies - self.on_loan - self.kept_for_reservations


class LibraryReport:
    """Answers questions about the whole library. Never changes anything.

    These questions join several tables together, which SQL does in one
    go, so this class reads the database directly instead of going through
    the repositories.
    """

    def __init__(self, db: Database, clock: Callable[[], date] | None = None) -> None:
        self._db = db
        self._clock = clock or date.today

    def overdue(self) -> list[OverdueRow]:
        """Every late book with who has it, most late first."""
        today = self._clock()
        rows = self._db.query(
            """
            SELECT l.loan_id, b.title, m.name, m.email, l.due_on
            FROM loans l
            JOIN books b   ON b.book_id = l.book_id
            JOIN members m ON m.member_id = l.member_id
            WHERE l.returned_on IS NULL AND l.due_on < ?
            ORDER BY l.due_on, l.loan_id
            """,
            (today.isoformat(),),
        )
        result = []
        for row in rows:
            due = date.fromisoformat(row["due_on"])
            result.append(OverdueRow(row["loan_id"], row["title"], row["name"], row["email"],
                                     due, (today - due).days))
        return result

    def most_borrowed(self, limit: int = 5) -> list[PopularRow]:
        """The books lent most often, ever."""
        rows = self._db.query(
            """
            SELECT b.title, b.author, COUNT(*) AS times
            FROM loans l JOIN books b ON b.book_id = l.book_id
            GROUP BY b.book_id
            ORDER BY times DESC, b.title COLLATE NOCASE
            LIMIT ?
            """,
            (limit,),
        )
        return [PopularRow(r["title"], r["author"], r["times"]) for r in rows]

    def members(self) -> list[MemberRow]:
        """Each member with how many books they have and what they owe."""
        rows = self._db.query(
            """
            SELECT m.member_id, m.name, m.member_type, m.status,
                   (SELECT COUNT(*) FROM loans l
                    WHERE l.member_id = m.member_id AND l.returned_on IS NULL) AS on_loan
            FROM members m
            ORDER BY m.member_id
            """
        )
        # Money is added up in Python, because SQLite would turn the text
        # amounts into floats and lose pennies.
        owed: dict[int, Decimal] = {}
        for fine in self._db.query("SELECT member_id, amount FROM fines WHERE paid_on IS NULL"):
            owed[fine["member_id"]] = owed.get(fine["member_id"], ZERO) + Decimal(fine["amount"])
        return [MemberRow(r["member_id"], r["name"], r["member_type"], r["status"],
                          r["on_loan"], owed.get(r["member_id"], ZERO)) for r in rows]

    def stock(self) -> StockSummary:
        today = self._clock().isoformat()
        row = self._db.query_one(
            """
            SELECT
              (SELECT COUNT(*) FROM books) AS titles,
              (SELECT COALESCE(SUM(copies), 0) FROM books) AS copies,
              (SELECT COUNT(*) FROM loans WHERE returned_on IS NULL) AS on_loan,
              (SELECT COUNT(*) FROM reservations
               WHERE status = 'ready' AND expires_on >= ?) AS kept
            """,
            (today,),
        )
        return StockSummary(row["titles"], row["copies"], row["on_loan"], row["kept"])

    def total_owed(self) -> Decimal:
        return sum((r.owed for r in self.members()), start=ZERO)


class TextFormatter:
    """Turns books, loans and reports into plain text tables."""

    def books(self, books: Sequence[Book], available: dict[int, int] | None = None) -> str:
        """available maps book_id to copies on the shelf, if known."""
        if not books:
            return "No books found."
        lines = [f"{'Id':<5}{'Title':<34}{'Author':<24}{'Year':>6}{'Free':>7}", "-" * 76]
        for book in books:
            free = f"{available[book.book_id]}/{book.copies}" if available else str(book.copies)
            lines.append(f"{book.book_id:<5}{_cut(book.title, 33):<34}{_cut(book.author, 23):<24}"
                         f"{book.year or '':>6}{free:>7}")
        return "\n".join(lines)

    def members(self, rows: Sequence[MemberRow]) -> str:
        if not rows:
            return "No members yet."
        lines = [f"{'Id':<5}{'Name':<26}{'Type':<9}{'Status':<11}{'Books':>6}{'Owes':>10}",
                 "-" * 67]
        for r in rows:
            lines.append(f"{r.member_id:<5}{_cut(r.name, 25):<26}{r.member_type:<9}"
                         f"{r.status:<11}{r.books_on_loan:>6}{format_money(r.owed):>10}")
        return "\n".join(lines)

    def loans(self, loans: Sequence[Loan], titles: dict[int, str], today: date) -> str:
        """titles maps book_id to title."""
        if not loans:
            return "No books on loan."
        lines = [f"{'Loan':<6}{'Title':<34}{'Due':<12}{'Renewed':>8}  Note", "-" * 70]
        for loan in loans:
            note = f"{loan.days_overdue(today)} days late" if loan.is_overdue(today) else ""
            lines.append(f"{loan.loan_id:<6}{_cut(titles.get(loan.book_id, '?'), 33):<34}"
                         f"{loan.due_on.isoformat():<12}{loan.renewals:>8}  {note}".rstrip())
        return "\n".join(lines)

    def reservations(self, reservations: Sequence[Reservation], titles: dict[int, str]) -> str:
        if not reservations:
            return "No reservations."
        lines = [f"{'Id':<6}{'Title':<34}{'Status':<10}Collect by", "-" * 62]
        for r in reservations:
            collect = r.expires_on.isoformat() if r.expires_on else ""
            lines.append(f"{r.reservation_id:<6}{_cut(titles.get(r.book_id, '?'), 33):<34}"
                         f"{r.status.value:<10}{collect}".rstrip())
        return "\n".join(lines)

    def fines(self, fines: Sequence[Fine]) -> str:
        if not fines:
            return "No fines."
        lines = [f"{'Id':<6}{'Loan':<6}{'Amount':>9}  {'Charged':<12}Paid", "-" * 45]
        for f in fines:
            paid = f.paid_on.isoformat() if f.paid_on else "not yet"
            lines.append(f"{f.fine_id:<6}{f.loan_id:<6}{format_money(f.amount):>9}  "
                         f"{f.charged_on.isoformat():<12}{paid}")
        return "\n".join(lines)

    def overdue(self, rows: Sequence[OverdueRow]) -> str:
        if not rows:
            return "Nothing is overdue."
        lines = [f"{'Loan':<6}{'Title':<30}{'Member':<22}{'Due':<12}{'Late':>6}", "-" * 76]
        for r in rows:
            lines.append(f"{r.loan_id:<6}{_cut(r.title, 29):<30}{_cut(r.member_name, 21):<22}"
                         f"{r.due_on.isoformat():<12}{r.days_late:>4} d")
        return "\n".join(lines)

    def popular(self, rows: Sequence[PopularRow]) -> str:
        if not rows:
            return "Nothing has been borrowed yet."
        lines = [f"{'Title':<34}{'Author':<26}{'Loans':>6}", "-" * 66]
        lines += [f"{_cut(r.title, 33):<34}{_cut(r.author, 25):<26}{r.times_borrowed:>6}"
                  for r in rows]
        return "\n".join(lines)

    def stock(self, summary: StockSummary) -> str:
        rows = [
            ("Titles", summary.titles),
            ("Copies owned", summary.copies),
            ("Out on loan", summary.on_loan),
            ("Kept for reservations", summary.kept_for_reservations),
            ("On the shelf", summary.on_shelf),
        ]
        return "\n".join(f"{label:<24}{value:>6}" for label, value in rows)


def _cut(text: str, width: int) -> str:
    """Shorten long text with "..." so the columns stay lined up."""
    return text if len(text) <= width else text[: width - 3] + "..."
