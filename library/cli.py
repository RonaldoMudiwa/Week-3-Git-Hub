"""The command line interface.

Each command opens the database, does one job and closes it again. Every
change is saved by the database straight away, so there's no save step.
Run it from the project root:

    python -m library add-book 0306406152 "Things Fall Apart" "Chinua Achebe" --copies 2
    python -m library join student "Amara Okafor" amara@example.com
    python -m library lend 1 1

Add --help after any command to see its options.
"""

from __future__ import annotations

import argparse
import sys
from abc import ABC, abstractmethod
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from .book import Book
from .csv_io import BookExporter, BookImporter
from .database import Database
from .exceptions import LibraryError
from .members import member_type_names
from .money import format_money
from .reports import LibraryReport, TextFormatter
from .service import Clock, Library

DEFAULT_FILE = Path("data") / "library.db"

# Given the --file path, opens the database to use.
DatabaseFactory = Callable[[Path], Database]


class Session:
    """What a command gets to work with while it runs."""

    def __init__(self, out: TextIO, library: Library | None = None,
                 report: LibraryReport | None = None) -> None:
        self.out = out
        self.formatter = TextFormatter()
        self._library = library
        self._report = report

    @property
    def library(self) -> Library:
        if self._library is None:
            raise RuntimeError("This command was run without a library.")
        return self._library

    @property
    def report(self) -> LibraryReport:
        if self._report is None:
            raise RuntimeError("This command was run without a library.")
        return self._report

    def say(self, text: str = "") -> None:
        print(text, file=self.out)

    def find_book(self, text: str) -> Book:
        """Accept a book id like 3, or an ISBN in any format."""
        cleaned = text.replace("-", "").replace(" ", "")
        if cleaned.isdigit() and len(cleaned) < 10:
            return self.library.get_book(int(cleaned))
        return self.library.find_book(text)

    def titles(self) -> dict[int, str]:
        return {book.book_id: book.title for book in self.library.books}


class Command(ABC):
    """One thing the user can ask for. Each command is its own small class,
    so a new one never means editing the others."""

    name = ""
    help = ""
    needs_library = True

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add this command's own options. Commands with none can skip it."""

    @abstractmethod
    def run(self, session: Session, args: argparse.Namespace) -> None:
        """Do the job. Raise a LibraryError if it can't be done."""


# ----------------------------------------------------------------------
# Books
# ----------------------------------------------------------------------

class AddBookCommand(Command):
    name = "add-book"
    help = "add a book to the catalogue"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("isbn", help="10 or 13 digits, dashes are fine")
        parser.add_argument("title", help="in quotes if it has spaces")
        parser.add_argument("author")
        parser.add_argument("--year", type=int)
        parser.add_argument("--copies", type=int, default=1)

    def run(self, session: Session, args: argparse.Namespace) -> None:
        book = session.library.add_book(args.isbn, args.title, args.author, args.year, args.copies)
        session.say(f"Added book {book.book_id}: {book} ({_copies(book.copies)}).")


class BooksCommand(Command):
    name = "books"
    help = "list or search the catalogue"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("text", nargs="?", help="words from the title or author")
        parser.add_argument("--author")
        parser.add_argument("--from-year", type=int)
        parser.add_argument("--to-year", type=int)
        parser.add_argument("--available", action="store_true", help="only books on the shelf")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        library = session.library
        books = library.search(args.text, author=args.author, year_from=args.from_year,
                               year_to=args.to_year, available_only=args.available)
        free = {book.book_id: library.available_copies(book.book_id) for book in books}
        session.say(session.formatter.books(books, free))


class CopiesCommand(Command):
    name = "copies"
    help = "change how many copies of a book the library owns"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("book", help="book id or ISBN")
        parser.add_argument("copies", type=int)

    def run(self, session: Session, args: argparse.Namespace) -> None:
        book = session.library.set_copies(session.find_book(args.book).book_id, args.copies)
        session.say(f"The library now owns {_copies(book.copies)} of {book.title}.")


class RemoveBookCommand(Command):
    name = "remove-book"
    help = "take a book that was never lent out of the catalogue"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("book", help="book id or ISBN")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        book = session.find_book(args.book)
        session.library.remove_book(book.book_id)
        session.say(f"Removed {book.title}.")


# ----------------------------------------------------------------------
# Members
# ----------------------------------------------------------------------

class JoinCommand(Command):
    name = "join"
    help = "sign up a new member"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("member_type", help=", ".join(member_type_names()))
        parser.add_argument("name", help="in quotes if it has spaces")
        parser.add_argument("email")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        member = session.library.register_member(args.member_type, args.name, args.email)
        session.say(f"Welcome, {member.name}. Your member number is {member.member_id}. "
                    f"You can borrow {member.max_loans} books for {member.loan_days} days.")


class MembersCommand(Command):
    name = "members"
    help = "list every member with their books and fines"

    def run(self, session: Session, args: argparse.Namespace) -> None:
        session.say(session.formatter.members(session.report.members()))


class _MemberStatusCommand(Command):
    """Shared by suspend and reinstate."""

    done = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("member", type=int, help="member number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        member = self.change(session.library, args.member)
        session.say(f"{member.name}'s card is {self.done}.")

    @abstractmethod
    def change(self, library: Library, member_id: int):
        """Make the change and return the member."""


class SuspendCommand(_MemberStatusCommand):
    name = "suspend"
    help = "stop a member borrowing"
    done = "suspended"

    def change(self, library: Library, member_id: int):
        return library.suspend_member(member_id)


class ReinstateCommand(_MemberStatusCommand):
    name = "reinstate"
    help = "let a suspended member borrow again"
    done = "active again"

    def change(self, library: Library, member_id: int):
        return library.reinstate_member(member_id)


# ----------------------------------------------------------------------
# Lending
# ----------------------------------------------------------------------

class LendCommand(Command):
    name = "lend"
    help = "lend a book to a member"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("book", help="book id or ISBN")
        parser.add_argument("member", type=int, help="member number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        book = session.find_book(args.book)
        loan = session.library.lend(book.book_id, args.member)
        session.say(f"Loan {loan.loan_id}: {book.title} is due back on {loan.due_on}.")


class ReturnCommand(Command):
    name = "return"
    help = "take a book back"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("loan", type=int, help="loan number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        receipt = session.library.give_back(args.loan)
        book = session.library.get_book(receipt.loan.book_id)
        session.say(f"{book.title} is back.")
        if receipt.loan.days_overdue(receipt.loan.returned_on):
            session.say(f"It was {receipt.loan.days_overdue(receipt.loan.returned_on)} days late.")
        if receipt.fine:
            session.say(f"Fine {receipt.fine.fine_id}: {format_money(receipt.fine.amount)}.")
        if receipt.held_for:
            member = session.library.get_member(receipt.held_for.member_id)
            session.say(f"Keep it aside for {member} until {receipt.held_for.expires_on}.")


class RenewCommand(Command):
    name = "renew"
    help = "keep a book for longer"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("loan", type=int, help="loan number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        loan = session.library.renew(args.loan)
        session.say(f"Loan {loan.loan_id} is now due on {loan.due_on}.")


class LoansCommand(Command):
    name = "loans"
    help = "show the books a member has"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("member", type=int, help="member number")
        parser.add_argument("--history", action="store_true", help="include returned books")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        library = session.library
        loans = library.history_for(args.member) if args.history else library.loans_for(args.member)
        session.say(session.formatter.loans(loans, session.titles(), library.today))


# ----------------------------------------------------------------------
# Reservations and fines
# ----------------------------------------------------------------------

class ReserveCommand(Command):
    name = "reserve"
    help = "join the queue for a book that's all out"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("book", help="book id or ISBN")
        parser.add_argument("member", type=int, help="member number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        book = session.find_book(args.book)
        reservation = session.library.reserve(book.book_id, args.member)
        place = len(session.library.queue_for(book.book_id))
        session.say(f"Reservation {reservation.reservation_id}: number {place} in the queue "
                    f"for {book.title}.")


class CancelCommand(Command):
    name = "cancel"
    help = "cancel a reservation"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("reservation", type=int, help="reservation number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        session.library.cancel_reservation(args.reservation)
        session.say(f"Reservation {args.reservation} cancelled.")


class ReservationsCommand(Command):
    name = "reservations"
    help = "show a member's reservations"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("member", type=int, help="member number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        reservations = session.library.reservations_for(args.member)
        session.say(session.formatter.reservations(reservations, session.titles()))


class FinesCommand(Command):
    name = "fines"
    help = "show a member's fines"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("member", type=int, help="member number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        library = session.library
        session.say(session.formatter.fines(library.fines_for(args.member)))
        session.say(f"Owed: {format_money(library.amount_owed(args.member))}")


class PayCommand(Command):
    name = "pay"
    help = "mark a fine as paid"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("fine", type=int, help="fine number")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        fine = session.library.pay_fine(args.fine)
        session.say(f"Paid {format_money(fine.amount)}. Thank you.")


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------

class ReportCommand(Command):
    name = "report"
    help = "the librarian's view: late books, popular books, members and stock"

    def run(self, session: Session, args: argparse.Namespace) -> None:
        report, fmt = session.report, session.formatter
        sections = [
            ("Overdue", fmt.overdue(report.overdue())),
            ("Most borrowed", fmt.popular(report.most_borrowed())),
            ("Members", fmt.members(report.members())),
            ("Stock", fmt.stock(report.stock())),
        ]
        for title, table in sections:
            session.say(f"=== {title} ===")
            session.say(table)
            session.say()
        session.say(f"Total fines owed: {format_money(report.total_owed())}")


class ImportBooksCommand(Command):
    name = "import-books"
    help = "add books from a CSV file (columns: isbn, title, author, year, copies)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("csv_file", type=Path)
        parser.add_argument("--skip-existing", action="store_true",
                            help="leave books already in the catalogue instead of stopping")

    def run(self, session: Session, args: argparse.Namespace) -> None:
        result = BookImporter(session.library).import_file(args.csv_file, args.skip_existing)
        session.say(f"Added {len(result.added)} book(s).")
        if result.skipped:
            session.say(f"Skipped {len(result.skipped)} already in the catalogue.")


class ExportBooksCommand(Command):
    name = "export-books"
    help = "save the catalogue to a CSV file"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("csv_file", type=Path)

    def run(self, session: Session, args: argparse.Namespace) -> None:
        count = BookExporter(session.library).export_file(args.csv_file)
        session.say(f"Saved {count} book(s) to {args.csv_file}.")


class DemoCommand(Command):
    name = "demo"
    help = "a short tour with made up members (your real library isn't touched)"
    needs_library = False

    def run(self, session: Session, args: argparse.Namespace) -> None:
        from . import demo  # only loaded when someone asks for it

        with redirect_stdout(session.out):
            demo.main()


def _copies(count: int) -> str:
    return f"{count} copy" if count == 1 else f"{count} copies"


def default_commands() -> list[Command]:
    return [
        AddBookCommand(), BooksCommand(), CopiesCommand(), RemoveBookCommand(),
        JoinCommand(), MembersCommand(), SuspendCommand(), ReinstateCommand(),
        LendCommand(), ReturnCommand(), RenewCommand(), LoansCommand(),
        ReserveCommand(), CancelCommand(), ReservationsCommand(),
        FinesCommand(), PayCommand(), ReportCommand(),
        ImportBooksCommand(), ExportBooksCommand(), DemoCommand(),
    ]


class LibraryCLI:
    """Reads what was typed and runs the matching command.

    The database, clock and output are passed in, so tests can run every
    command against a throwaway database.
    """

    def __init__(
        self,
        open_database: DatabaseFactory | None = None,
        commands: Sequence[Command] | None = None,
        clock: Clock | None = None,
        out: TextIO | None = None,
        err: TextIO | None = None,
    ) -> None:
        self._open_database = open_database or Database
        self._clock = clock or date.today
        self._out = out or sys.stdout
        self._err = err or sys.stderr
        self._commands: dict[str, Command] = {}
        for command in (commands if commands is not None else default_commands()):
            if command.name in self._commands:
                raise ValueError(f"Two commands are called {command.name!r}.")
            self._commands[command.name] = command

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(self._commands)

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="python -m library",
                                         description="A small library you run from the terminal.")
        parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                            help=f"the database file (default: {DEFAULT_FILE})")
        subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")
        for command in self._commands.values():
            sub = subparsers.add_parser(command.name, help=command.help, description=command.help)
            command.add_arguments(sub)
        return parser

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Run one command. Returns 0 if it worked, 1 if the library said no.

        Typing mistakes, like a missing loan number, are caught by argparse,
        which prints the usage and exits with 2.
        """
        args = self.build_parser().parse_args(argv)
        command = self._commands[args.command]
        try:
            if not command.needs_library:
                command.run(Session(self._out), args)
                return 0
            with self._open_database(args.file) as db:
                session = Session(self._out, Library.open(db, self._clock),
                                  LibraryReport(db, self._clock))
                command.run(session, args)
        except LibraryError as error:
            print(f"Error: {error}", file=self._err)
            return 1
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    return LibraryCLI().run(argv)
