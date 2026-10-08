"""A book in the library's catalogue."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .exceptions import ValidationError
from .isbn import normalise_isbn
from .validation import clean_text, whole_number

# Printing presses started around 1450, so nothing older is a real book year.
EARLIEST_YEAR = 1450
LATEST_YEAR = 2100


@dataclass(frozen=True)
class Book:
    """One title in the catalogue, and how many copies the library owns.

    It can't be changed after it's made. Use with_changes() to get an
    updated copy, the same way you'd print a new label rather than scribble
    on the old one.

        >>> Book("0-306-40615-2", "Data Structures", "A. Writer", 1999, copies=2).isbn
        '9780306406157'
    """

    isbn: str
    title: str
    author: str
    year: int | None = None
    copies: int = 1
    book_id: int | None = None  # given out by the database when the book is saved

    def __post_init__(self) -> None:
        # Frozen dataclasses need object.__setattr__ to store the cleaned values.
        object.__setattr__(self, "isbn", normalise_isbn(self.isbn))
        object.__setattr__(self, "title", clean_text(self.title, "Title"))
        object.__setattr__(self, "author", clean_text(self.author, "Author"))
        object.__setattr__(self, "copies", whole_number(self.copies, "Copies", minimum=1))
        if self.year is not None:
            year = whole_number(self.year, "Year")
            if not EARLIEST_YEAR <= year <= LATEST_YEAR:
                raise ValidationError(f"Year must be between {EARLIEST_YEAR} and {LATEST_YEAR}.")
        if self.book_id is not None:
            whole_number(self.book_id, "Book id", minimum=1)

    def with_changes(self, **changes) -> "Book":
        """A new Book with some fields changed. All the checks run again."""
        return replace(self, **changes)

    def __str__(self) -> str:
        year = f", {self.year}" if self.year else ""
        return f"{self.title} by {self.author}{year}"
