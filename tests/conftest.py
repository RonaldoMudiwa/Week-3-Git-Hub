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
