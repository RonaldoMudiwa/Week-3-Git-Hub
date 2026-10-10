"""Library Management System.

Books, members and loans, saved in a SQLite database.

    from library import Book, AdultMember
"""

from .book import Book
from .database import Database
from .enums import MemberStatus
from .exceptions import (
    AlreadyBorrowedError,
    AlreadyReturnedError,
    BookInUseError,
    BookNotFoundError,
    DatabaseError,
    DuplicateError,
    LibraryError,
    LoanError,
    LoanLimitError,
    LoanNotFoundError,
    MemberNotActiveError,
    MemberNotFoundError,
    NoCopiesAvailableError,
    NotFoundError,
    OverdueLoansError,
    RenewalError,
    ValidationError,
)
from .isbn import normalise_isbn
from .loans import Loan, LoanRepository, SQLiteLoanRepository
from .members import (
    AdultMember,
    ChildMember,
    Member,
    StudentMember,
    member_class_for,
    member_type_names,
    register_member_type,
)
from .repositories import (
    BookRepository,
    MemberRepository,
    SQLiteBookRepository,
    SQLiteMemberRepository,
)
from .service import Library

__version__ = "0.3.0"

__all__ = [
    "Library",
    "Book",
    "Loan",
    "Member",
    "AdultMember",
    "StudentMember",
    "ChildMember",
    "member_class_for",
    "member_type_names",
    "register_member_type",
    "MemberStatus",
    "Database",
    "BookRepository",
    "MemberRepository",
    "SQLiteBookRepository",
    "SQLiteMemberRepository",
    "LoanRepository",
    "SQLiteLoanRepository",
    "normalise_isbn",
    "LibraryError",
    "ValidationError",
    "MemberNotActiveError",
    "LoanError",
    "LoanLimitError",
    "NoCopiesAvailableError",
    "AlreadyBorrowedError",
    "OverdueLoansError",
    "AlreadyReturnedError",
    "RenewalError",
    "BookInUseError",
    "LoanNotFoundError",
    "NotFoundError",
    "BookNotFoundError",
    "MemberNotFoundError",
    "DuplicateError",
    "DatabaseError",
    "__version__",
]
