"""Reservations: a queue of members waiting for a book that's all out.

Like the waiting list at a busy restaurant. When a copy comes back, the
first person in the queue has it kept for them for a few days. If they
don't collect it in time, it goes to the next person.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import date

from .database import Database
from .enums import ReservationStatus
from .exceptions import ReservationNotFoundError, ValidationError
from .validation import whole_number


@dataclass(frozen=True)
class Reservation:
    book_id: int
    member_id: int
    reserved_on: date
    status: ReservationStatus = ReservationStatus.WAITING
    expires_on: date | None = None  # only set once a copy is kept for them
    reservation_id: int | None = None

    def __post_init__(self) -> None:
        whole_number(self.book_id, "Book id", minimum=1)
        whole_number(self.member_id, "Member id", minimum=1)
        if not isinstance(self.reserved_on, date):
            raise ValidationError("reserved_on must be a date.")
        if not isinstance(self.status, ReservationStatus):
            raise ValidationError("status must be a ReservationStatus.")
        if self.status is ReservationStatus.READY and self.expires_on is None:
            raise ValidationError("A ready reservation needs an expiry date.")

    @property
    def is_active(self) -> bool:
        """Still waiting, or a copy is being kept for them."""
        return self.status in (ReservationStatus.WAITING, ReservationStatus.READY)

    def is_held(self, today: date) -> bool:
        """True if a copy is on the shelf for this member right now."""
        return (self.status is ReservationStatus.READY and self.expires_on is not None
                and today <= self.expires_on)

    def with_changes(self, **changes) -> "Reservation":
        return replace(self, **changes)


class ReservationRepository(ABC):
    @abstractmethod
    def add(self, reservation: Reservation) -> Reservation:
        """Save a new reservation and return it with its id."""

    @abstractmethod
    def get(self, reservation_id: int) -> Reservation:
        """Raises ReservationNotFoundError if there's no such reservation."""

    @abstractmethod
    def update(self, reservation: Reservation) -> None:
        """Save a change of status."""

    @abstractmethod
    def for_book(self, book_id: int, status: ReservationStatus) -> list[Reservation]:
        """Reservations for a book with this status, first come first served."""

    @abstractmethod
    def active_for_member(self, member_id: int) -> list[Reservation]:
        """A member's waiting and ready reservations."""

    @abstractmethod
    def all_with_status(self, status: ReservationStatus) -> list[Reservation]:
        """Every reservation with this status, oldest first."""


class SQLiteReservationRepository(ReservationRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, reservation: Reservation) -> Reservation:
        if reservation.reservation_id is not None:
            raise ValidationError("This reservation has already been saved.")
        try:
            cursor = self._db.execute(
                "INSERT INTO reservations (book_id, member_id, reserved_on, status, expires_on) "
                "VALUES (?, ?, ?, ?, ?)",
                (reservation.book_id, reservation.member_id, reservation.reserved_on.isoformat(),
                 reservation.status.value, _iso(reservation.expires_on)),
            )
        except sqlite3.IntegrityError:
            raise ValidationError("That book or member doesn't exist.") from None
        return reservation.with_changes(reservation_id=cursor.lastrowid)

    def get(self, reservation_id: int) -> Reservation:
        row = self._db.query_one("SELECT * FROM reservations WHERE reservation_id = ?",
                                 (reservation_id,))
        if row is None:
            raise ReservationNotFoundError(f"No reservation with id {reservation_id}.")
        return self._to_reservation(row)

    def update(self, reservation: Reservation) -> None:
        if reservation.reservation_id is None:
            raise ValidationError("Save the reservation with add() before updating it.")
        cursor = self._db.execute(
            "UPDATE reservations SET status = ?, expires_on = ? WHERE reservation_id = ?",
            (reservation.status.value, _iso(reservation.expires_on), reservation.reservation_id),
        )
        if cursor.rowcount == 0:
            raise ReservationNotFoundError(f"No reservation with id {reservation.reservation_id}.")

    def for_book(self, book_id: int, status: ReservationStatus) -> list[Reservation]:
        return self._many("SELECT * FROM reservations WHERE book_id = ? AND status = ? "
                          "ORDER BY reserved_on, reservation_id", (book_id, status.value))

    def active_for_member(self, member_id: int) -> list[Reservation]:
        return self._many("SELECT * FROM reservations WHERE member_id = ? AND status IN (?, ?) "
                          "ORDER BY reserved_on, reservation_id",
                          (member_id, ReservationStatus.WAITING.value,
                           ReservationStatus.READY.value))

    def all_with_status(self, status: ReservationStatus) -> list[Reservation]:
        return self._many("SELECT * FROM reservations WHERE status = ? "
                          "ORDER BY reserved_on, reservation_id", (status.value,))

    def _many(self, sql: str, params: tuple) -> list[Reservation]:
        return [self._to_reservation(row) for row in self._db.query(sql, params)]

    @staticmethod
    def _to_reservation(row: sqlite3.Row) -> Reservation:
        expires = row["expires_on"]
        return Reservation(row["book_id"], row["member_id"], date.fromisoformat(row["reserved_on"]),
                           ReservationStatus(row["status"]),
                           date.fromisoformat(expires) if expires else None,
                           row["reservation_id"])


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None
