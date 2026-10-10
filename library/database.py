"""The SQLite database: opening it, setting up the tables, and transactions.

SQLite keeps the whole database in one file and comes with Python, so there
is nothing extra to install.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .exceptions import DatabaseError

IN_MEMORY = ":memory:"

# Each entry upgrades the database by one version. Never edit an old entry,
# because databases already out there have run it. Add a new one instead.
MIGRATIONS: tuple[tuple[str, ...], ...] = (
    # Version 1: books and members
    (
        """
        CREATE TABLE books (
            book_id  INTEGER PRIMARY KEY,
            isbn     TEXT    NOT NULL UNIQUE,
            title    TEXT    NOT NULL,
            author   TEXT    NOT NULL,
            year     INTEGER,
            copies   INTEGER NOT NULL CHECK (copies >= 1)
        )
        """,
        """
        CREATE TABLE members (
            member_id    INTEGER PRIMARY KEY,
            member_type  TEXT NOT NULL,
            name         TEXT NOT NULL,
            email        TEXT NOT NULL UNIQUE,
            joined_on    TEXT NOT NULL,
            status       TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_books_title ON books (title)",
        "CREATE INDEX idx_books_author ON books (author)",
    ),
    # Version 2: loans. RESTRICT stops a book or member with loans being deleted.
    (
        """
        CREATE TABLE loans (
            loan_id      INTEGER PRIMARY KEY,
            book_id      INTEGER NOT NULL REFERENCES books (book_id) ON DELETE RESTRICT,
            member_id    INTEGER NOT NULL REFERENCES members (member_id) ON DELETE RESTRICT,
            borrowed_on  TEXT    NOT NULL,
            due_on       TEXT    NOT NULL,
            returned_on  TEXT,
            renewals     INTEGER NOT NULL DEFAULT 0 CHECK (renewals >= 0)
        )
        """,
        "CREATE INDEX idx_loans_member ON loans (member_id, returned_on)",
        "CREATE INDEX idx_loans_book ON loans (book_id, returned_on)",
    ),
)


class Database:
    """One open SQLite database.

    Use it in a with block so it always gets closed:

        with Database("data/library.db") as db:
            ...
    """

    def __init__(self, path: str | Path = IN_MEMORY) -> None:
        self._path = str(path)
        if self._path != IN_MEMORY:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        try:
            # isolation_level=None means we start and finish transactions
            # ourselves, in transaction() below.
            self._connection = sqlite3.connect(self._path, isolation_level=None)
        except sqlite3.Error as error:
            raise DatabaseError(f"Could not open {self._path}: {error}") from error
        self._connection.row_factory = sqlite3.Row
        self._depth = 0
        try:
            # SQLite leaves foreign key checks off unless asked.
            self.execute("PRAGMA foreign_keys = ON")
            self._migrate()
        except Exception:
            self._connection.close()
            raise

    @property
    def path(self) -> str:
        return self._path

    @property
    def schema_version(self) -> int:
        return self.execute("PRAGMA user_version").fetchone()[0]

    # ------------------------------------------------------------------
    # Running SQL
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run one statement. Always pass values as params, never paste them
        into the SQL text, so a title like "Bobby'); DROP TABLE books" is
        just a title.

        sqlite3.IntegrityError is passed on as it is, so the caller can say
        what was duplicated. Any other database problem becomes a DatabaseError.
        """
        try:
            return self._connection.execute(sql, params)
        except sqlite3.IntegrityError:
            raise
        except sqlite3.Error as error:
            raise DatabaseError(f"Database problem: {error}") from error

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Everything inside happens together, or none of it does.

        Like paying at a till: the money and the shopping change hands
        together, or the sale is cancelled. Using it inside another
        transaction just joins the outer one.
        """
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return

        self.execute("BEGIN")
        self._depth = 1
        try:
            yield
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self.execute("COMMIT")
        finally:
            self._depth = 0

    # ------------------------------------------------------------------
    # Setting up and closing
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        """Bring the tables up to date, one version at a time."""
        current = self.schema_version
        if current > len(MIGRATIONS):
            raise DatabaseError(
                f"{self._path} was made by a newer version of this program "
                f"(database version {current}, this program knows up to {len(MIGRATIONS)})."
            )
        for version in range(current + 1, len(MIGRATIONS) + 1):
            with self.transaction():
                for statement in MIGRATIONS[version - 1]:
                    self.execute(statement)
                # PRAGMA can't take a ? placeholder. version is our own int, so this is safe.
                self.execute(f"PRAGMA user_version = {version}")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Database({self._path!r})"
