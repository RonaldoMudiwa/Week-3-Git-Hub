"""All the errors this package can raise.

Everything inherits from LibraryError, so one except clause catches the lot.

    LibraryError
    |-- ValidationError
    |-- MemberNotActiveError
    |-- LoanError
    |   |-- LoanLimitError
    |   |-- NoCopiesAvailableError
    |   |-- AlreadyBorrowedError
    |   |-- OverdueLoansError
    |   |-- AlreadyReturnedError
    |   |-- RenewalError
    |   |-- FinesOwedError
    |-- ReservationError
    |-- FineError
    |-- BookInUseError
    |-- NotFoundError
    |   |-- BookNotFoundError
    |   |-- MemberNotFoundError
    |   |-- LoanNotFoundError
    |   |-- ReservationNotFoundError
    |   |-- FineNotFoundError
    |-- DuplicateError
    |-- DatabaseError
"""

from __future__ import annotations


class LibraryError(Exception):
    """Base class for every error in this package. Never raised directly."""


class ValidationError(LibraryError):
    """A value isn't allowed, e.g. a blank title or a bad ISBN."""


class MemberNotActiveError(LibraryError):
    """The member is suspended, so they can't borrow."""


class LoanError(LibraryError):
    """A book can't be lent, returned or renewed. Catch this for all of them."""


class LoanLimitError(LoanError):
    """The member already has as many books as their card allows."""


class NoCopiesAvailableError(LoanError):
    """Every copy of the book is out."""


class AlreadyBorrowedError(LoanError):
    """The member already has a copy of this book."""


class OverdueLoansError(LoanError):
    """The member has a late book, so they can't borrow more until it's back."""


class AlreadyReturnedError(LoanError):
    """The loan was already finished."""


class RenewalError(LoanError):
    """The loan can't be extended, e.g. it's late or renewed too many times."""


class FinesOwedError(LoanError):
    """The member owes too much in fines to borrow more."""


class ReservationError(LibraryError):
    """A book can't be reserved, e.g. a copy is free or it's already reserved."""


class FineError(LibraryError):
    """A fine can't be paid, e.g. it was already paid."""


class BookInUseError(LibraryError):
    """The book can't be removed or have copies taken away while it's lent out."""


class NotFoundError(LibraryError):
    """Something asked for by id doesn't exist."""


class BookNotFoundError(NotFoundError):
    """No book has that id or ISBN."""


class MemberNotFoundError(NotFoundError):
    """No member has that id."""


class LoanNotFoundError(NotFoundError):
    """No loan has that id."""


class ReservationNotFoundError(NotFoundError):
    """No reservation has that id."""


class FineNotFoundError(NotFoundError):
    """No fine has that id."""


class DuplicateError(LibraryError):
    """Something unique is already taken, e.g. an ISBN or an email."""


class DatabaseError(LibraryError):
    """The database couldn't be opened or used."""
