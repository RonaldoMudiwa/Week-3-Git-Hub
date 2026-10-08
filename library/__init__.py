"""Library Management System.

Books, members and loans, saved in a SQLite database.

    from library import Book, AdultMember
"""

from .book import Book
from .enums import MemberStatus
from .exceptions import LibraryError, LoanLimitError, MemberNotActiveError, ValidationError
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

__version__ = "0.1.0"

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
    "normalise_isbn",
    "LibraryError",
    "ValidationError",
    "MemberNotActiveError",
    "LoanLimitError",
    "__version__",
]
