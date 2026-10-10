"""The Library: the front desk that lends books and takes them back.

It holds the rules that involve more than one thing at once, like "is a
copy free?" or "does this member have a late book?". Books, members and
loans each look after their own details.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, ContextManager

from .book import Book
from .database import Database
from .exceptions import (
    AlreadyBorrowedError,
    AlreadyReturnedError,
    BookInUseError,
    BookNotFoundError,
    NoCopiesAvailableError,
    OverdueLoansError,
    RenewalError,
)
from .loans import Loan, LoanRepository, SQLiteLoanRepository
from .members import Member, member_class_for
from .repositories import (
    BookRepository,
    MemberRepository,
    SQLiteBookRepository,
    SQLiteMemberRepository,
)
from .validation import whole_number

Clock = Callable[[], date]
# Returns a with block where everything happens together or not at all.
TransactionFactory = Callable[[], ContextManager[None]]


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
        transaction: TransactionFactory,
        clock: Clock | None = None,
    ) -> None:
        self._books = books
        self._members = members
        self._loans = loans
        self._transaction = transaction
        self._clock = clock or date.today

    @classmethod
    def open(cls, db: Database, clock: Clock | None = None) -> "Library":
        """A Library that keeps everything in this database."""
        return cls(SQLiteBookRepository(db), SQLiteMemberRepository(db),
                   SQLiteLoanRepository(db), db.transaction, clock)

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

    def available_copies(self, book_id: int) -> int:
        book = self._books.get(book_id)
        return book.copies - len(self._loans.active_for_book(book_id))

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
            member = self._members.get(member_id)
            book = self._books.get(book_id)
            today = self.today
            current = self._loans.active_for_member(member_id)

            member.check_can_borrow(len(current))
            late = [loan for loan in current if loan.is_overdue(today)]
            if late:
                raise OverdueLoansError(f"{member.name} has {len(late)} late book(s). "
                                        f"They need to come back first.")
            if any(loan.book_id == book_id for loan in current):
                raise AlreadyBorrowedError(f"{member.name} already has a copy of {book.title}.")
            if self._free_copies(book) <= 0:
                raise NoCopiesAvailableError(f"Every copy of {book.title} is out.")

            loan = Loan(book.book_id, member_id, today, member.due_date(today))
            return self._loans.add(loan)

    def give_back(self, loan_id: int) -> Loan:
        """Return a book. Raises AlreadyReturnedError if it was already returned."""
        with self._transaction():
            loan = self._loans.get(loan_id)
            if loan.is_returned:
                raise AlreadyReturnedError(f"Loan {loan_id} was returned on {loan.returned_on}.")
            returned = loan.with_changes(returned_on=self.today)
            self._loans.update(returned)
            return returned

    def renew(self, loan_id: int) -> Loan:
        """Keep a book for longer. The new due date counts from today.

        Raises:
            RenewalError: If it's returned, late, or renewed too many times.
        """
        with self._transaction():
            loan = self._loans.get(loan_id)
            member = self._members.get(loan.member_id)
            today = self.today
            if loan.is_returned:
                raise RenewalError("A returned book can't be renewed.")
            if loan.is_overdue(today):
                raise RenewalError("A late book can't be renewed. Please bring it back.")
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

    def _free_copies(self, book: Book) -> int:
        return book.copies - len(self._loans.active_for_book(book.book_id))
