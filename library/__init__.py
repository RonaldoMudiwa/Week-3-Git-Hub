"""Library Management System.

Books, members and loans, saved in a SQLite database.

    from library import Book, AdultMember
"""

from .book import Book
from .csv_io import BookExporter, BookImporter, ImportResult
from .database import Database
from .enums import MemberStatus, ReservationStatus
from .exceptions import (
    AlreadyBorrowedError,
    AlreadyReturnedError,
    BookInUseError,
    BookNotFoundError,
    DatabaseError,
    DuplicateError,
    FineError,
    FineNotFoundError,
    FinesOwedError,
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
    ReservationError,
    ReservationNotFoundError,
    ValidationError,
)
from .fines import DailyFine, Fine, FinePolicy, FineRepository, NoFine, SQLiteFineRepository
from .isbn import normalise_isbn
from .loans import Loan, LoanRepository, SQLiteLoanRepository
from .money import format_money, to_money
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
from .reservations import Reservation, ReservationRepository, SQLiteReservationRepository
from .reports import (
    LibraryReport,
    MemberRow,
    OverdueRow,
    PopularRow,
    StockSummary,
    TextFormatter,
)
from .search import BookSearch
from .service import Library, ReturnReceipt

__version__ = "1.0.0"

__all__ = [
    "Library",
    "ReturnReceipt",
    "BookSearch",
    "BookImporter",
    "BookExporter",
    "ImportResult",
    "LibraryReport",
    "TextFormatter",
    "OverdueRow",
    "PopularRow",
    "MemberRow",
    "StockSummary",
    "Book",
    "Loan",
    "Reservation",
    "Fine",
    "FinePolicy",
    "DailyFine",
    "NoFine",
    "Member",
    "AdultMember",
    "StudentMember",
    "ChildMember",
    "member_class_for",
    "member_type_names",
    "register_member_type",
    "MemberStatus",
    "ReservationStatus",
    "to_money",
    "format_money",
    "Database",
    "BookRepository",
    "MemberRepository",
    "SQLiteBookRepository",
    "SQLiteMemberRepository",
    "LoanRepository",
    "SQLiteLoanRepository",
    "ReservationRepository",
    "SQLiteReservationRepository",
    "FineRepository",
    "SQLiteFineRepository",
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
    "FinesOwedError",
    "ReservationError",
    "FineError",
    "BookInUseError",
    "LoanNotFoundError",
    "ReservationNotFoundError",
    "FineNotFoundError",
    "NotFoundError",
    "BookNotFoundError",
    "MemberNotFoundError",
    "DuplicateError",
    "DatabaseError",
    "__version__",
]
