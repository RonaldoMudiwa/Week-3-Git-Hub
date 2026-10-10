"""Loans: one copy of a book lent to one member."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import date

from .database import Database
from .exceptions import LoanNotFoundError, NotFoundError, ValidationError
from .validation import whole_number


@dataclass(frozen=True)
class Loan:
    """A record of who has which book and when it's due back.

    Like the date stamp inside a library book. Once made it isn't changed.
    Returning or renewing gives a new Loan with the new dates.
    """

    book_id: int
    member_id: int
    borrowed_on: date
    due_on: date
    returned_on: date | None = None
    renewals: int = 0
    loan_id: int | None = None

    def __post_init__(self) -> None:
        whole_number(self.book_id, "Book id", minimum=1)
        whole_number(self.member_id, "Member id", minimum=1)
        whole_number(self.renewals, "Renewals")
        for name in ("borrowed_on", "due_on"):
            if not isinstance(getattr(self, name), date):
                raise ValidationError(f"{name} must be a date.")
        if self.due_on < self.borrowed_on:
            raise ValidationError("A loan can't be due before it was borrowed.")
        if self.returned_on is not None:
            if not isinstance(self.returned_on, date):
                raise ValidationError("returned_on must be a date.")
            if self.returned_on < self.borrowed_on:
                raise ValidationError("A book can't come back before it went out.")

    @property
    def is_returned(self) -> bool:
        return self.returned_on is not None

    def days_overdue(self, today: date) -> int:
        """How many days late. For a returned book, how late it was when it came back."""
        end = self.returned_on or today
        return max((end - self.due_on).days, 0)

    def is_overdue(self, today: date) -> bool:
        return not self.is_returned and self.days_overdue(today) > 0

    def with_changes(self, **changes) -> "Loan":
        return replace(self, **changes)


class LoanRepository(ABC):
    @abstractmethod
    def add(self, loan: Loan) -> Loan:
        """Save a new loan and return it with its loan_id."""

    @abstractmethod
    def get(self, loan_id: int) -> Loan:
        """Raises LoanNotFoundError if there's no such loan."""

    @abstractmethod
    def update(self, loan: Loan) -> None:
        """Save a return or a renewal."""

    @abstractmethod
    def active_for_member(self, member_id: int) -> list[Loan]:
        """Books the member has right now, oldest first."""

    @abstractmethod
    def history_for_member(self, member_id: int) -> list[Loan]:
        """Every loan the member has ever had, newest first."""

    @abstractmethod
    def active_for_book(self, book_id: int) -> list[Loan]:
        """Copies of this book that are out right now."""

    @abstractmethod
    def count_for_book(self, book_id: int) -> int:
        """How many times the book has ever been lent, returned or not."""

    @abstractmethod
    def all_active(self) -> list[Loan]:
        """Every book that's out, soonest due first."""


class SQLiteLoanRepository(LoanRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, loan: Loan) -> Loan:
        if loan.loan_id is not None:
            raise ValidationError("This loan has already been saved.")
        try:
            cursor = self._db.execute(
                "INSERT INTO loans (book_id, member_id, borrowed_on, due_on, returned_on, renewals) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (loan.book_id, loan.member_id, loan.borrowed_on.isoformat(),
                 loan.due_on.isoformat(), _iso(loan.returned_on), loan.renewals),
            )
        except sqlite3.IntegrityError:
            # The foreign keys refused it.
            raise NotFoundError("That book or member doesn't exist.") from None
        return loan.with_changes(loan_id=cursor.lastrowid)

    def get(self, loan_id: int) -> Loan:
        row = self._db.query_one("SELECT * FROM loans WHERE loan_id = ?", (loan_id,))
        if row is None:
            raise LoanNotFoundError(f"No loan with id {loan_id}.")
        return self._to_loan(row)

    def update(self, loan: Loan) -> None:
        if loan.loan_id is None:
            raise ValidationError("Save the loan with add() before updating it.")
        cursor = self._db.execute(
            "UPDATE loans SET due_on = ?, returned_on = ?, renewals = ? WHERE loan_id = ?",
            (loan.due_on.isoformat(), _iso(loan.returned_on), loan.renewals, loan.loan_id),
        )
        if cursor.rowcount == 0:
            raise LoanNotFoundError(f"No loan with id {loan.loan_id}.")

    def active_for_member(self, member_id: int) -> list[Loan]:
        return self._many("SELECT * FROM loans WHERE member_id = ? AND returned_on IS NULL "
                          "ORDER BY borrowed_on, loan_id", (member_id,))

    def history_for_member(self, member_id: int) -> list[Loan]:
        return self._many("SELECT * FROM loans WHERE member_id = ? "
                          "ORDER BY borrowed_on DESC, loan_id DESC", (member_id,))

    def active_for_book(self, book_id: int) -> list[Loan]:
        return self._many("SELECT * FROM loans WHERE book_id = ? AND returned_on IS NULL "
                          "ORDER BY due_on, loan_id", (book_id,))

    def count_for_book(self, book_id: int) -> int:
        return self._db.query_one("SELECT COUNT(*) FROM loans WHERE book_id = ?", (book_id,))[0]

    def all_active(self) -> list[Loan]:
        return self._many("SELECT * FROM loans WHERE returned_on IS NULL ORDER BY due_on, loan_id")

    def _many(self, sql: str, params: tuple = ()) -> list[Loan]:
        return [self._to_loan(row) for row in self._db.query(sql, params)]

    @staticmethod
    def _to_loan(row: sqlite3.Row) -> Loan:
        returned = row["returned_on"]
        return Loan(row["book_id"], row["member_id"], date.fromisoformat(row["borrowed_on"]),
                    date.fromisoformat(row["due_on"]),
                    date.fromisoformat(returned) if returned else None,
                    row["renewals"], row["loan_id"])


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None
