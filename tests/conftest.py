"""Shared test helpers."""

from __future__ import annotations

from datetime import date, timedelta

import pytest


class FakeClock:
    """A calendar the tests control, so results don't depend on today's date."""

    def __init__(self, start: date = date(2026, 10, 1)) -> None:
        self.today = start

    def __call__(self) -> date:
        return self.today

    def advance(self, days: int) -> None:
        self.today += timedelta(days=days)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def db():
    """A fresh database in memory for each test. Nothing is written to disk."""
    from library import Database

    database = Database()
    yield database
    database.close()


@pytest.fixture
def library(db, clock):
    """A Library in memory, with a calendar the test controls."""
    from library import Library

    return Library.open(db, clock)


ACHEBE_ISBN = "9780306406157"
ADICHIE_ISBN = "080442957X"


@pytest.fixture
def stocked(library):
    """Two books (ids 1 and 2) and one member of each type (ids 1, 2 and 3)."""
    library.add_book(ACHEBE_ISBN, "Things Fall Apart", "Chinua Achebe", 1958, copies=2)
    library.add_book(ADICHIE_ISBN, "Purple Hibiscus", "Chimamanda Adichie", 2003)
    library.register_member("adult", "Ronaldo Mudiwa", "ronaldo@example.com")
    library.register_member("student", "Amara Okafor", "amara@example.com")
    library.register_member("child", "Tendai Moyo", "tendai@example.com")
    return library
