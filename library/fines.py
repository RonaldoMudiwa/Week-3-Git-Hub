"""Late fines: the rules for working them out, and the fines themselves."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from .database import Database
from .exceptions import FineNotFoundError, ValidationError
from .money import ZERO, format_money, to_money
from .validation import whole_number


class FinePolicy(ABC):
    """How much to charge for a book that comes back late.

    Each member type has its own policy, so a child's late book can be free
    while an adult pays by the day. New rules are new classes.
    """

    @abstractmethod
    def fine_for(self, days_late: int) -> Decimal:
        """The charge for a book this many days late. Zero for on time."""


class NoFine(FinePolicy):
    def fine_for(self, days_late: int) -> Decimal:
        return ZERO

    def __repr__(self) -> str:
        return "NoFine()"


class DailyFine(FinePolicy):
    """A set amount for every day late, up to a maximum.

        >>> DailyFine("0.25", maximum="10").fine_for(6)
        Decimal('1.50')
    """

    def __init__(self, per_day: Decimal | int | str, maximum: Decimal | int | str) -> None:
        self._per_day = to_money(per_day)
        self._maximum = to_money(maximum)
        if self._per_day <= ZERO or self._maximum <= ZERO:
            raise ValidationError("Fine amounts must be above zero.")

    @property
    def per_day(self) -> Decimal:
        return self._per_day

    @property
    def maximum(self) -> Decimal:
        return self._maximum

    def fine_for(self, days_late: int) -> Decimal:
        days = whole_number(days_late, "Days late")
        # Capped, so a book lost for a year doesn't cost more than buying it.
        return min(self._per_day * days, self._maximum)

    def __repr__(self) -> str:
        return f"DailyFine({str(self._per_day)!r}, maximum={str(self._maximum)!r})"


@dataclass(frozen=True)
class Fine:
    """Money a member owes for one late loan."""

    loan_id: int
    member_id: int
    amount: Decimal
    charged_on: date
    paid_on: date | None = None
    fine_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_money(self.amount))
        if self.amount <= ZERO:
            raise ValidationError("A fine must be more than £0.00.")
        if not isinstance(self.charged_on, date):
            raise ValidationError("charged_on must be a date.")
        if self.paid_on is not None and self.paid_on < self.charged_on:
            raise ValidationError("A fine can't be paid before it was charged.")

    @property
    def is_paid(self) -> bool:
        return self.paid_on is not None

    def with_changes(self, **changes) -> "Fine":
        return replace(self, **changes)

    def __str__(self) -> str:
        state = f"paid {self.paid_on}" if self.is_paid else "unpaid"
        return f"{format_money(self.amount)} for loan {self.loan_id} ({state})"


class FineRepository(ABC):
    @abstractmethod
    def add(self, fine: Fine) -> Fine:
        """Save a new fine and return it with its fine_id."""

    @abstractmethod
    def get(self, fine_id: int) -> Fine:
        """Raises FineNotFoundError if there's no such fine."""

    @abstractmethod
    def update(self, fine: Fine) -> None:
        """Save a payment."""

    @abstractmethod
    def for_member(self, member_id: int, unpaid_only: bool = False) -> list[Fine]:
        """A member's fines, oldest first."""

    @abstractmethod
    def all_unpaid(self) -> list[Fine]:
        """Every fine still owed, oldest first."""


class SQLiteFineRepository(FineRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, fine: Fine) -> Fine:
        if fine.fine_id is not None:
            raise ValidationError("This fine has already been saved.")
        try:
            cursor = self._db.execute(
                "INSERT INTO fines (loan_id, member_id, amount, charged_on, paid_on) "
                "VALUES (?, ?, ?, ?, ?)",
                (fine.loan_id, fine.member_id, str(fine.amount), fine.charged_on.isoformat(),
                 fine.paid_on.isoformat() if fine.paid_on else None),
            )
        except sqlite3.IntegrityError:
            raise ValidationError(f"Loan {fine.loan_id} is missing or already has a fine.") from None
        return fine.with_changes(fine_id=cursor.lastrowid)

    def get(self, fine_id: int) -> Fine:
        row = self._db.query_one("SELECT * FROM fines WHERE fine_id = ?", (fine_id,))
        if row is None:
            raise FineNotFoundError(f"No fine with id {fine_id}.")
        return self._to_fine(row)

    def update(self, fine: Fine) -> None:
        if fine.fine_id is None:
            raise ValidationError("Save the fine with add() before updating it.")
        cursor = self._db.execute(
            "UPDATE fines SET paid_on = ? WHERE fine_id = ?",
            (fine.paid_on.isoformat() if fine.paid_on else None, fine.fine_id),
        )
        if cursor.rowcount == 0:
            raise FineNotFoundError(f"No fine with id {fine.fine_id}.")

    def for_member(self, member_id: int, unpaid_only: bool = False) -> list[Fine]:
        sql = "SELECT * FROM fines WHERE member_id = ?"
        if unpaid_only:
            sql += " AND paid_on IS NULL"
        rows = self._db.query(sql + " ORDER BY charged_on, fine_id", (member_id,))
        return [self._to_fine(row) for row in rows]

    def all_unpaid(self) -> list[Fine]:
        rows = self._db.query("SELECT * FROM fines WHERE paid_on IS NULL ORDER BY charged_on, fine_id")
        return [self._to_fine(row) for row in rows]

    @staticmethod
    def _to_fine(row: sqlite3.Row) -> Fine:
        paid = row["paid_on"]
        return Fine(row["loan_id"], row["member_id"], Decimal(row["amount"]),
                    date.fromisoformat(row["charged_on"]),
                    date.fromisoformat(paid) if paid else None, row["fine_id"])


def total(fines: list[Fine]) -> Decimal:
    return sum((f.amount for f in fines), start=ZERO)
