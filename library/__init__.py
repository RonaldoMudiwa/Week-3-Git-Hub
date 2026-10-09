"""Library Management System.

Books, members and loans, saved in a SQLite database.

    from library import Book, AdultMember
"""

from .book import Book
from .database import Database
from .enums import MemberStatus
from .exceptions import (
    BookNotFoundError,
    DatabaseError,
    DuplicateError,
    LibraryError,
    LoanLimitError,
    MemberNotActiveError,
    MemberNotFoundError,
    NotFoundError,
    ValidationError,
)
from .isbn import normalise_isbn
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

__version__ = "0.2.0"

__all__ = [
    "Book",
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
    "normalise_isbn",
    "LibraryError",
    "ValidationError",
    "MemberNotActiveError",
    "LoanLimitError",
    "NotFoundError",
    "BookNotFoundError",
    "MemberNotFoundError",
    "DuplicateError",
    "DatabaseError",
    "__version__",
]
