"""All the errors this package can raise.

Everything inherits from LibraryError, so one except clause catches the lot.
"""

from __future__ import annotations


class LibraryError(Exception):
    """Base class for every error in this package. Never raised directly."""


class ValidationError(LibraryError):
    """A value isn't allowed, e.g. a blank title or a bad ISBN."""


class MemberNotActiveError(LibraryError):
    """The member is suspended, so they can't borrow."""


class LoanLimitError(LibraryError):
    """The member already has as many books as their card allows."""


class NotFoundError(LibraryError):
    """Something asked for by id doesn't exist."""


class BookNotFoundError(NotFoundError):
    """No book has that id or ISBN."""


class MemberNotFoundError(NotFoundError):
    """No member has that id."""


class DuplicateError(LibraryError):
    """Something unique is already taken, e.g. an ISBN or an email."""


class DatabaseError(LibraryError):
    """The database couldn't be opened or used."""
