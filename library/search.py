"""Searching the catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .exceptions import ValidationError


@dataclass(frozen=True)
class BookSearch:
    """What to look for. Leave a field as None to ignore it.

        BookSearch(text="achebe")                  # in the title or author
        BookSearch(author="adichie", year_from=2000)
        BookSearch(available_on=date.today())      # only books on the shelf

    The repository turns this into SQL, so the rest of the program never
    has to write any.
    """

    text: str | None = None
    title: str | None = None
    author: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    available_on: date | None = None

    def __post_init__(self) -> None:
        for name in ("text", "title", "author"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, str):
                    raise ValidationError(f"Search {name} must be text.")
                # Blank means "don't filter on this".
                object.__setattr__(self, name, value.strip() or None)
        for name in ("year_from", "year_to"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValidationError(f"{name} must be a whole number.")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValidationError("year_from can't be after year_to.")
        if self.available_on is not None and not isinstance(self.available_on, date):
            raise ValidationError("available_on must be a date.")


def like_pattern(text: str) -> str:
    """Turn text into a LIKE pattern that matches it anywhere.

    % and _ are wildcards in LIKE, so they're escaped with a backslash.
    Otherwise searching for "100%" would match everything starting "100".
    """
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
