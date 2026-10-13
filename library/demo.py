"""A quick tour of the library with made up members. Run it from the project root:

    python -m library demo

It uses a database in memory and a pretend calendar, so it never touches
your real library and shows a month going by in a second.
"""

from __future__ import annotations

from datetime import date, timedelta

from .database import Database
from .exceptions import LibraryError
from .money import format_money
from .reports import LibraryReport, TextFormatter


class PretendCalendar:
    def __init__(self, start: date) -> None:
        self.today = start

    def __call__(self) -> date:
        return self.today

    def skip(self, days: int) -> None:
        self.today += timedelta(days=days)
        print(f"\n... {days} days later ({self.today}) ...")


def main() -> None:
    from .service import Library

    calendar = PretendCalendar(date(2026, 10, 1))
    with Database() as db:
        library = Library.open(db, calendar)
        report = LibraryReport(db, calendar)
        fmt = TextFormatter()

        achebe = library.add_book("0306406152", "Things Fall Apart", "Chinua Achebe", 1958, copies=2)
        adichie = library.add_book("080442957X", "Purple Hibiscus", "Chimamanda Ngozi Adichie", 2003)
        library.add_book("9781234567897", "Half of a Yellow Sun", "Chimamanda Ngozi Adichie", 2006)

        ronaldo = library.register_member("adult", "Ronaldo Mudiwa", "ronaldo@example.com")
        amara = library.register_member("student", "Amara Okafor", "amara@example.com")
        tendai = library.register_member("child", "Tendai Moyo", "tendai@example.com")

        print("The catalogue")
        print(fmt.books(library.books, {b.book_id: b.copies for b in library.books}))

        print(f"\nOn {calendar.today}")
        first = library.lend(adichie.book_id, ronaldo.member_id)
        print(f"{ronaldo.name} borrows Purple Hibiscus, due {first.due_on}")
        library.lend(achebe.book_id, tendai.member_id)
        print(f"{tendai.name} borrows Things Fall Apart, due in {tendai.loan_days} days")
        library.reserve(adichie.book_id, amara.member_id)
        print(f"{amara.name} reserves Purple Hibiscus, because it's out")

        calendar.skip(25)
        receipt = library.give_back(first.loan_id)
        print(f"{ronaldo.name} brings Purple Hibiscus back "
              f"{receipt.loan.days_overdue(calendar.today)} days late "
              f"and is fined {format_money(receipt.fine.amount)}")
        print(f"The copy is kept for {amara.name} until {receipt.held_for.expires_on}")
        library.lend(adichie.book_id, amara.member_id)
        print(f"{amara.name} collects it")

        print("\nThe librarian's report")
        print(fmt.overdue(report.overdue()))
        print()
        print(fmt.members(report.members()))

        print("\nThings the library refuses to do")
        attempts = [
            ("Lend a book that's all out",
             lambda: library.lend(adichie.book_id, ronaldo.member_id)),
            ("Lend to a member with a late book",
             lambda: library.lend(adichie.book_id, tendai.member_id)),
            ("Add the same book twice",
             lambda: library.add_book("978-0-306-40615-7", "Copy", "Someone")),
            ("Join twice with one email",
             lambda: library.register_member("adult", "Ron", "RONALDO@example.com")),
        ]
        for label, attempt in attempts:
            try:
                attempt()
            except LibraryError as error:
                print(f"{label}: {type(error).__name__}: {error}")
