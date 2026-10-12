"""Saving and finding books and members.

The rest of the program only uses the abstract BookRepository and
MemberRepository, so the SQLite versions could be swapped for something
else without changing any other code.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import date

from .book import Book
from .database import Database
from .enums import MemberStatus
from .exceptions import BookNotFoundError, DuplicateError, MemberNotFoundError, ValidationError
from .isbn import normalise_isbn
from .members import Member, member_class_for
from .search import BookSearch, like_pattern


class BookRepository(ABC):
    @abstractmethod
    def add(self, book: Book) -> Book:
        """Save a new book and return it with its book_id filled in."""

    @abstractmethod
    def get(self, book_id: int) -> Book:
        """Raises BookNotFoundError if there's no such book."""

    @abstractmethod
    def find_by_isbn(self, isbn: str) -> Book | None:
        """Any ISBN format works. None if the library doesn't have it."""

    @abstractmethod
    def update(self, book: Book) -> None:
        """Save changes to a book that already has a book_id."""

    @abstractmethod
    def remove(self, book_id: int) -> None:
        """Delete a book from the catalogue."""

    @abstractmethod
    def all(self) -> list[Book]:
        """Every book, sorted by title."""

    @abstractmethod
    def search(self, query: BookSearch) -> list[Book]:
        """Books matching every part of the query, sorted by title."""


class MemberRepository(ABC):
    @abstractmethod
    def add(self, member: Member) -> Member:
        """Save a new member. Their member_id is filled in."""

    @abstractmethod
    def get(self, member_id: int) -> Member:
        """Raises MemberNotFoundError if there's no such member."""

    @abstractmethod
    def find_by_email(self, email: str) -> Member | None:
        """Case doesn't matter. None if nobody has that email."""

    @abstractmethod
    def update(self, member: Member) -> None:
        """Save changes to a member, e.g. a new email or being suspended."""

    @abstractmethod
    def all(self) -> list[Member]:
        """Every member, in the order they joined."""


class SQLiteBookRepository(BookRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, book: Book) -> Book:
        if book.book_id is not None:
            raise ValidationError("This book has already been saved.")
        try:
            cursor = self._db.execute(
                "INSERT INTO books (isbn, title, author, year, copies) VALUES (?, ?, ?, ?, ?)",
                (book.isbn, book.title, book.author, book.year, book.copies),
            )
        except sqlite3.IntegrityError:
            raise DuplicateError(f"A book with ISBN {book.isbn} is already in the catalogue.") from None
        return book.with_changes(book_id=cursor.lastrowid)

    def get(self, book_id: int) -> Book:
        row = self._db.query_one("SELECT * FROM books WHERE book_id = ?", (book_id,))
        if row is None:
            raise BookNotFoundError(f"No book with id {book_id}.")
        return self._to_book(row)

    def find_by_isbn(self, isbn: str) -> Book | None:
        row = self._db.query_one("SELECT * FROM books WHERE isbn = ?", (normalise_isbn(isbn),))
        return self._to_book(row) if row else None

    def update(self, book: Book) -> None:
        if book.book_id is None:
            raise ValidationError("Save the book with add() before updating it.")
        try:
            cursor = self._db.execute(
                "UPDATE books SET isbn = ?, title = ?, author = ?, year = ?, copies = ? "
                "WHERE book_id = ?",
                (book.isbn, book.title, book.author, book.year, book.copies, book.book_id),
            )
        except sqlite3.IntegrityError:
            raise DuplicateError(f"Another book already has ISBN {book.isbn}.") from None
        if cursor.rowcount == 0:
            raise BookNotFoundError(f"No book with id {book.book_id}.")

    def remove(self, book_id: int) -> None:
        cursor = self._db.execute("DELETE FROM books WHERE book_id = ?", (book_id,))
        if cursor.rowcount == 0:
            raise BookNotFoundError(f"No book with id {book_id}.")

    def all(self) -> list[Book]:
        rows = self._db.query("SELECT * FROM books ORDER BY title COLLATE NOCASE, book_id")
        return [self._to_book(row) for row in rows]

    def search(self, query: BookSearch) -> list[Book]:
        # Each part adds one condition and its values. Values always go in
        # params, never into the SQL text.
        conditions: list[str] = []
        params: list[object] = []
        if query.text:
            conditions.append("(title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\')")
            params += [like_pattern(query.text)] * 2
        if query.title:
            conditions.append("title LIKE ? ESCAPE '\\'")
            params.append(like_pattern(query.title))
        if query.author:
            conditions.append("author LIKE ? ESCAPE '\\'")
            params.append(like_pattern(query.author))
        if query.year_from is not None:
            conditions.append("year >= ?")
            params.append(query.year_from)
        if query.year_to is not None:
            conditions.append("year <= ?")
            params.append(query.year_to)
        if query.available_on is not None:
            # Copies owned, minus copies lent out, minus copies kept for a reservation.
            conditions.append(
                "copies"
                " - (SELECT COUNT(*) FROM loans l"
                "    WHERE l.book_id = books.book_id AND l.returned_on IS NULL)"
                " - (SELECT COUNT(*) FROM reservations r"
                "    WHERE r.book_id = books.book_id AND r.status = 'ready' AND r.expires_on >= ?)"
                " > 0"
            )
            params.append(query.available_on.isoformat())

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self._db.query(f"SELECT * FROM books{where} ORDER BY title COLLATE NOCASE, book_id",
                              params)
        return [self._to_book(row) for row in rows]

    @staticmethod
    def _to_book(row: sqlite3.Row) -> Book:
        return Book(row["isbn"], row["title"], row["author"], row["year"],
                    row["copies"], row["book_id"])


class SQLiteMemberRepository(MemberRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, member: Member) -> Member:
        if member.member_id is not None:
            raise ValidationError("This member has already been saved.")
        try:
            cursor = self._db.execute(
                "INSERT INTO members (member_type, name, email, joined_on, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (member.MEMBER_TYPE, member.name, member.email,
                 member.joined_on.isoformat(), member.status.value),
            )
        except sqlite3.IntegrityError:
            raise DuplicateError(f"A member with email {member.email} already exists.") from None
        member.assign_id(cursor.lastrowid)
        return member

    def get(self, member_id: int) -> Member:
        row = self._db.query_one("SELECT * FROM members WHERE member_id = ?", (member_id,))
        if row is None:
            raise MemberNotFoundError(f"No member with id {member_id}.")
        return self._to_member(row)

    def find_by_email(self, email: str) -> Member | None:
        row = self._db.query_one("SELECT * FROM members WHERE email = ?",
                                 (str(email).strip().lower(),))
        return self._to_member(row) if row else None

    def update(self, member: Member) -> None:
        if member.member_id is None:
            raise ValidationError("Save the member with add() before updating them.")
        try:
            cursor = self._db.execute(
                "UPDATE members SET name = ?, email = ?, status = ? WHERE member_id = ?",
                (member.name, member.email, member.status.value, member.member_id),
            )
        except sqlite3.IntegrityError:
            raise DuplicateError(f"Another member already uses {member.email}.") from None
        if cursor.rowcount == 0:
            raise MemberNotFoundError(f"No member with id {member.member_id}.")

    def all(self) -> list[Member]:
        return [self._to_member(row)
                for row in self._db.query("SELECT * FROM members ORDER BY member_id")]

    @staticmethod
    def _to_member(row: sqlite3.Row) -> Member:
        member_class = member_class_for(row["member_type"])
        return member_class(row["name"], row["email"], date.fromisoformat(row["joined_on"]),
                            MemberStatus(row["status"]), row["member_id"])
