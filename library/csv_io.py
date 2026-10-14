"""Loading books from a spreadsheet, and saving the catalogue to one.

CSV is the plain text format Excel and Google Sheets can open and save.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .book import Book
from .exceptions import DuplicateError, LibraryError, ValidationError
from .service import Library

COLUMNS = ("isbn", "title", "author", "year", "copies")
REQUIRED = ("isbn", "title", "author")


@dataclass(frozen=True)
class ImportResult:
    added: tuple[Book, ...]
    skipped: tuple[str, ...]   # ISBNs already in the catalogue


class BookImporter:
    """Adds every book in a CSV file, or none of them.

    If line 40 has a mistake, the first 39 aren't half added. The whole file
    is checked first and then saved in one transaction.
    """

    def __init__(self, library: Library) -> None:
        self._library = library

    def import_file(self, path: str | Path, skip_existing: bool = False) -> ImportResult:
        """
        Args:
            skip_existing: If True, books already in the catalogue are left
                alone instead of stopping the import.

        Raises:
            ValidationError: If the file can't be read or a line is wrong.
                The message says which line.
        """
        books = self._read(Path(path))
        added, skipped = [], []
        with self._library.transaction():
            for line_number, book in books:
                if self._library.has_book(book.isbn):
                    if skip_existing:
                        skipped.append(book.isbn)
                        continue
                    raise DuplicateError(f"Line {line_number}: ISBN {book.isbn} is already "
                                         f"in the catalogue. Use skip_existing to leave it.")
                added.append(self._library.add_book(book.isbn, book.title, book.author,
                                                    book.year, book.copies))
        return ImportResult(tuple(added), tuple(skipped))

    def _read(self, path: Path) -> list[tuple[int, Book]]:
        try:
            # utf-8-sig drops the hidden mark Excel puts at the start of the file.
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
                headings = rows[0].keys() if rows else []
        except OSError as error:
            raise ValidationError(f"Could not read {path}: {error}") from error
        except UnicodeDecodeError:
            raise ValidationError(f"{path} isn't a UTF-8 text file. Save it as CSV UTF-8.") from None
        if not rows:
            raise ValidationError(f"{path} has no books in it.")

        # Headings can be in any case, e.g. "ISBN" or "Title".
        lookup = {str(h).strip().lower(): h for h in headings if h is not None}
        missing = [c for c in REQUIRED if c not in lookup]
        if missing:
            raise ValidationError(f"{path} is missing the column(s): {', '.join(missing)}.")

        books, seen = [], set()
        for line_number, row in enumerate(rows, start=2):  # line 1 is the headings
            try:
                book = self._to_book(row, lookup)
            except LibraryError as error:
                raise ValidationError(f"Line {line_number}: {error}") from error
            if book.isbn in seen:
                raise ValidationError(f"Line {line_number}: ISBN {book.isbn} is in the file twice.")
            seen.add(book.isbn)
            books.append((line_number, book))
        return books

    @staticmethod
    def _to_book(row: dict, lookup: dict[str, str]) -> Book:
        def cell(name: str) -> str:
            heading = lookup.get(name)
            return (row.get(heading) or "").strip() if heading else ""

        return Book(cell("isbn"), cell("title"), cell("author"),
                    _number(cell("year"), "Year") if cell("year") else None,
                    _number(cell("copies"), "Copies") if cell("copies") else 1)


class BookExporter:
    """Saves the whole catalogue as CSV, with how many copies are on the shelf."""

    def __init__(self, library: Library) -> None:
        self._library = library

    def export_file(self, path: str | Path) -> int:
        """Write the file and return how many books were in it."""
        path = Path(path)
        books = self._library.books
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([*COLUMNS, "on_shelf"])
                for book in books:
                    writer.writerow([book.isbn, book.title, book.author, book.year or "",
                                     book.copies, self._library.available_copies(book.book_id)])
        except OSError as error:
            raise ValidationError(f"Could not write {path}: {error}") from error
        return len(books)


def _number(text: str, field_name: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValidationError(f"{field_name} should be a whole number, got {text!r}.") from None
