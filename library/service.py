"""The Library: the front desk that lends books and takes them back.

It holds the rules that involve more than one thing at once, like "is a
copy free?" or "does this member have a late book?". Books, members and
loans each look after their own details.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, ContextManager

from .book import Book
from .database import Database
from .enums import ReservationStatus
from .exceptions import (
    AlreadyBorrowedError,
    AlreadyReturnedError,
    BookInUseError,
    BookNotFoundError,
    FineError,
    FinesOwedError,
    MemberNotActiveError,
    NoCopiesAvailableError,
    OverdueLoansError,
    RenewalError,
    ReservationError,
)
from .fines import Fine, FineRepository, SQLiteFineRepository, total
from .loans import Loan, LoanRepository, SQLiteLoanRepository
from .members import Member, member_class_for
from .money import format_money, to_money
from .repositories import (
    BookRepository,
    MemberRepository,
    SQLiteBookRepository,
    SQLiteMemberRepository,
)
from .reservations import Reservation, ReservationRepository, SQLiteReservationRepository
from .search import BookSearch
from .validation import whole_number

Clock = Callable[[], date]
# Returns a with block where everything happens together or not at all.
TransactionFactory = Callable[[], ContextManager[None]]

HOLD_DAYS = 3                    # how long a reserved copy is kept on the shelf
FINE_LIMIT = Decimal("5.00")     # owe this much or more and borrowing stops


@dataclass(frozen=True)
class ReturnReceipt:
    """What happened when a book came back."""

    loan: Loan
    fine: Fine | None = None                 # charged if it was late
    held_for: Reservation | None = None      # the copy is now kept for this person


class Library:
    """Lends books to members and keeps the loans in order.

    It only uses the abstract repositories, so it doesn't know or care that
    they happen to be SQLite. For the normal setup use Library.open(db).
    """

    def __init__(
        self,
        books: BookRepository,
        members: MemberRepository,
        loans: LoanRepository,
        reservations: ReservationRepository,
        fines: FineRepository,
        transaction: TransactionFactory,
        clock: Clock | None = None,
        hold_days: int = HOLD_DAYS,
        fine_limit: Decimal | int | str = FINE_LIMIT,
    ) -> None:
        self._books = books
        self._members = members
        self._loans = loans
        self._reservations = reservations
        self._fines = fines
        self._transaction = transaction
        self._clock = clock or date.today
        self._hold_days = whole_number(hold_days, "Hold days", minimum=1)
        self._fine_limit = to_money(fine_limit)

    @classmethod
    def open(cls, db: Database, clock: Clock | None = None, **settings) -> "Library":
        """A Library that keeps everything in this database.

        settings can change hold_days or fine_limit.
        """
        return cls(SQLiteBookRepository(db), SQLiteMemberRepository(db),
                   SQLiteLoanRepository(db), SQLiteReservationRepository(db),
                   SQLiteFineRepository(db), db.transaction, clock, **settings)

    @property
    def today(self) -> date:
        return self._clock()

    # ------------------------------------------------------------------
    # Books
    # ------------------------------------------------------------------

    def add_book(self, isbn: str, title: str, author: str, year: int | None = None,
                 copies: int = 1) -> Book:
        return self._books.add(Book(isbn, title, author, year, copies))

    def get_book(self, book_id: int) -> Book:
        return self._books.get(book_id)

    def find_book(self, isbn: str) -> Book:
        """Look a book up by ISBN. Raises BookNotFoundError if it isn't here."""
        book = self._books.find_by_isbn(isbn)
        if book is None:
            raise BookNotFoundError(f"No book with ISBN {isbn}.")
        return book

    @property
    def books(self) -> list[Book]:
        return self._books.all()

    def search(self, text: str | None = None, *, title: str | None = None,
               author: str | None = None, year_from: int | None = None,
               year_to: int | None = None, available_only: bool = False) -> list[Book]:
        """Find books. Every part given must match, e.g. search(author="achebe")."""
        query = BookSearch(text, title, author, year_from, year_to,
                           self.today if available_only else None)
        return self._books.search(query)

    def available_copies(self, book_id: int) -> int:
        """Copies on the shelf that anyone can borrow. Copies kept for a
        reservation don't count."""
        return self._free_copies(self._books.get(book_id))

    def set_copies(self, book_id: int, copies: int) -> Book:
        """Change how many copies the library owns, e.g. after buying more.

        Raises:
            BookInUseError: If that's fewer than are lent out right now.
        """
        with self._transaction():
            book = self._books.get(book_id)
            on_loan = len(self._loans.active_for_book(book_id))
            if whole_number(copies, "Copies", minimum=1) < on_loan:
                raise BookInUseError(f"{on_loan} copies of {book.title} are out, "
                                     f"so the library can't own fewer than that.")
            updated = book.with_changes(copies=copies)
            self._books.update(updated)
            # New copies go to anyone waiting first.
            self._serve_queue(updated)
            return updated

    def remove_book(self, book_id: int) -> None:
        """Take a book out of the catalogue. Only allowed if it was never lent,
        so no member's history ever points at a missing book."""
        with self._transaction():
            book = self._books.get(book_id)
            if self._loans.count_for_book(book_id):
                raise BookInUseError(f"{book.title} has loan history, so it can't be removed.")
            self._books.remove(book_id)

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def register_member(self, member_type: str, name: str, email: str) -> Member:
        """Sign someone up, e.g. register_member("student", "Amara", "amara@example.com")."""
        member = member_class_for(member_type)(name, email, joined_on=self.today)
        return self._members.add(member)

    def get_member(self, member_id: int) -> Member:
        return self._members.get(member_id)

    @property
    def members(self) -> list[Member]:
        return self._members.all()

    def suspend_member(self, member_id: int) -> Member:
        member = self._members.get(member_id)
        member.suspend()
        self._members.update(member)
        return member

    def reinstate_member(self, member_id: int) -> Member:
        member = self._members.get(member_id)
        member.reinstate()
        self._members.update(member)
        return member

    # ------------------------------------------------------------------
    # Lending
    # ------------------------------------------------------------------

    def lend(self, book_id: int, member_id: int) -> Loan:
        """Lend one copy of a book to a member.

        All the checks and the new loan happen in one transaction, so two
        people can't both get the last copy.

        Raises:
            MemberNotActiveError: If the member is suspended.
            OverdueLoansError: If they have a late book.
            LoanLimitError: If they have as many books as their card allows.
            AlreadyBorrowedError: If they already have a copy of this book.
            NoCopiesAvailableError: If every copy is out.
        """
        with self._transaction():
            self._expire_old_holds()
            member = self._members.get(member_id)
            book = self._books.get(book_id)
            today = self.today
            current = self._loans.active_for_member(member_id)

            member.check_can_borrow(len(current))
            late = [loan for loan in current if loan.is_overdue(today)]
            if late:
                raise OverdueLoansError(f"{member.name} has {len(late)} late book(s). "
                                        f"They need to come back first.")
            owed = total(self._fines.for_member(member_id, unpaid_only=True))
            if owed >= self._fine_limit:
                raise FinesOwedError(f"{member.name} owes {format_money(owed)} in fines. "
                                     f"Borrowing stops at {format_money(self._fine_limit)}.")
            if any(loan.book_id == book_id for loan in current):
                raise AlreadyBorrowedError(f"{member.name} already has a copy of {book.title}.")

            # A copy kept for this member's reservation is theirs to take.
            mine = self._reservation_of(member_id, book_id)
            held_for_them = mine is not None and mine.is_held(today)
            if not held_for_them and self._free_copies(book) <= 0:
                raise NoCopiesAvailableError(f"Every copy of {book.title} is out or reserved.")

            loan = self._loans.add(Loan(book.book_id, member_id, today, member.due_date(today)))
            if mine is not None:
                self._reservations.update(mine.with_changes(status=ReservationStatus.COLLECTED))
            return loan

    def give_back(self, loan_id: int) -> ReturnReceipt:
        """Return a book.

        If it's late, a fine is charged using the member's fine rules. If
        someone is waiting for the book, the copy is kept for them.

        Raises:
            AlreadyReturnedError: If it was already returned.
        """
        with self._transaction():
            self._expire_old_holds()
            loan = self._loans.get(loan_id)
            if loan.is_returned:
                raise AlreadyReturnedError(f"Loan {loan_id} was returned on {loan.returned_on}.")
            today = self.today
            returned = loan.with_changes(returned_on=today)
            self._loans.update(returned)

            fine = None
            member = self._members.get(loan.member_id)
            amount = member.fine_policy.fine_for(returned.days_overdue(today))
            if amount > 0:
                fine = self._fines.add(Fine(loan.loan_id, loan.member_id, amount, today))

            held = self._serve_queue(self._books.get(loan.book_id))
            return ReturnReceipt(returned, fine, held[0] if held else None)

    def renew(self, loan_id: int) -> Loan:
        """Keep a book for longer. The new due date counts from today.

        Raises:
            RenewalError: If it's returned, late, or renewed too many times.
        """
        with self._transaction():
            self._expire_old_holds()
            loan = self._loans.get(loan_id)
            member = self._members.get(loan.member_id)
            today = self.today
            if loan.is_returned:
                raise RenewalError("A returned book can't be renewed.")
            if loan.is_overdue(today):
                raise RenewalError("A late book can't be renewed. Please bring it back.")
            if self._reservations.for_book(loan.book_id, ReservationStatus.WAITING):
                raise RenewalError("Someone has reserved this book, so it needs to come back.")
            if loan.renewals >= member.MAX_RENEWALS:
                raise RenewalError(f"This loan has already been renewed {loan.renewals} times, "
                                   f"the most a {member.MEMBER_TYPE} member can.")
            renewed = loan.with_changes(due_on=member.due_date(today), renewals=loan.renewals + 1)
            self._loans.update(renewed)
            return renewed

    def get_loan(self, loan_id: int) -> Loan:
        return self._loans.get(loan_id)

    def loans_for(self, member_id: int) -> list[Loan]:
        """The books a member has right now."""
        self._members.get(member_id)  # raises if they don't exist
        return self._loans.active_for_member(member_id)

    def history_for(self, member_id: int) -> list[Loan]:
        self._members.get(member_id)
        return self._loans.history_for_member(member_id)

    @property
    def active_loans(self) -> list[Loan]:
        return self._loans.all_active()

    # ------------------------------------------------------------------
    # Reservations
    # ------------------------------------------------------------------

    def reserve(self, book_id: int, member_id: int) -> Reservation:
        """Join the queue for a book whose copies are all out.

        Raises:
            MemberNotActiveError: If the member is suspended.
            ReservationError: If a copy is free, or they already have or
                reserved this book.
        """
        with self._transaction():
            self._expire_old_holds()
            member = self._members.get(member_id)
            book = self._books.get(book_id)
            if not member.is_active:
                raise MemberNotActiveError(f"{member.name}'s card is suspended.")
            if self._reservation_of(member_id, book_id) is not None:
                raise ReservationError(f"{member.name} has already reserved {book.title}.")
            if any(loan.book_id == book_id for loan in self._loans.active_for_member(member_id)):
                raise ReservationError(f"{member.name} already has {book.title}.")
            if self._free_copies(book) > 0:
                raise ReservationError(f"A copy of {book.title} is on the shelf. Just borrow it.")
            return self._reservations.add(Reservation(book_id, member_id, self.today))

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        """Leave the queue. A copy kept for them goes to the next person."""
        with self._transaction():
            reservation = self._reservations.get(reservation_id)
            if not reservation.is_active:
                raise ReservationError(f"Reservation {reservation_id} is already "
                                       f"{reservation.status.value}.")
            cancelled = reservation.with_changes(status=ReservationStatus.CANCELLED)
            self._reservations.update(cancelled)
            self._serve_queue(self._books.get(reservation.book_id))
            return cancelled

    def get_reservation(self, reservation_id: int) -> Reservation:
        return self._reservations.get(reservation_id)

    def reservations_for(self, member_id: int) -> list[Reservation]:
        self._members.get(member_id)
        return self._reservations.active_for_member(member_id)

    def queue_for(self, book_id: int) -> list[Reservation]:
        """Everyone still waiting for a book, first in line first."""
        self._books.get(book_id)
        return self._reservations.for_book(book_id, ReservationStatus.WAITING)

    def process_expired_holds(self) -> list[Reservation]:
        """Give up kept copies that weren't collected in time. Lending and
        returning do this anyway, so it only needs calling to tidy up."""
        with self._transaction():
            return self._expire_old_holds()

    # ------------------------------------------------------------------
    # Fines
    # ------------------------------------------------------------------

    def fines_for(self, member_id: int, unpaid_only: bool = False) -> list[Fine]:
        self._members.get(member_id)
        return self._fines.for_member(member_id, unpaid_only)

    def amount_owed(self, member_id: int) -> Decimal:
        return total(self.fines_for(member_id, unpaid_only=True))

    def pay_fine(self, fine_id: int) -> Fine:
        fine = self._fines.get(fine_id)
        if fine.is_paid:
            raise FineError(f"Fine {fine_id} was already paid on {fine.paid_on}.")
        paid = fine.with_changes(paid_on=self.today)
        self._fines.update(paid)
        return paid

    @property
    def unpaid_fines(self) -> list[Fine]:
        return self._fines.all_unpaid()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _free_copies(self, book: Book) -> int:
        """Copies that are neither lent out nor kept for a reservation."""
        today = self.today
        on_loan = len(self._loans.active_for_book(book.book_id))
        held = sum(1 for r in self._reservations.for_book(book.book_id, ReservationStatus.READY)
                   if r.is_held(today))
        return book.copies - on_loan - held

    def _reservation_of(self, member_id: int, book_id: int) -> Reservation | None:
        for reservation in self._reservations.active_for_member(member_id):
            if reservation.book_id == book_id:
                return reservation
        return None

    def _serve_queue(self, book: Book) -> list[Reservation]:
        """Keep any free copies for the people at the front of the queue."""
        expires = self.today + timedelta(days=self._hold_days)
        served = []
        for waiting in self._reservations.for_book(book.book_id, ReservationStatus.WAITING):
            if self._free_copies(book) <= 0:
                break
            ready = waiting.with_changes(status=ReservationStatus.READY, expires_on=expires)
            self._reservations.update(ready)
            served.append(ready)
        return served

    def _expire_old_holds(self) -> list[Reservation]:
        today = self.today
        expired = []
        for reservation in self._reservations.all_with_status(ReservationStatus.READY):
            if not reservation.is_held(today):
                gone = reservation.with_changes(status=ReservationStatus.EXPIRED)
                self._reservations.update(gone)
                expired.append(gone)
        for book_id in {r.book_id for r in expired}:
            self._serve_queue(self._books.get(book_id))
        return expired
