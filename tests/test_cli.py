"""Tests for the command line interface.

Each test gets its own database file in tmp_path, so real data is never touched.
"""

from __future__ import annotations

import argparse
import io
import runpy
import sys

import pytest

from library import Database, Library
from library.cli import Command, LibraryCLI, Session, default_commands, main


class Terminal:
    """Runs commands one after another against one database file."""

    def __init__(self, path, clock) -> None:
        self.path = path
        self.clock = clock

    def run(self, *argv: str, commands=None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        cli = LibraryCLI(commands=commands, clock=self.clock, out=out, err=err)
        code = cli.run(["--file", str(self.path), *argv])
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv: str, **kwargs) -> str:
        code, out, err = self.run(*argv, **kwargs)
        assert code == 0, err
        return out

    def fails(self, *argv: str) -> str:
        code, out, err = self.run(*argv)
        assert code == 1
        assert err.startswith("Error: ")
        return err

    def library(self) -> Library:
        """Open the database directly to check what was saved."""
        return Library.open(Database(self.path), self.clock)


@pytest.fixture
def term(tmp_path, clock) -> Terminal:
    return Terminal(tmp_path / "library.db", clock)


@pytest.fixture
def ready(term) -> Terminal:
    """Two books and two members: Amara (1, student) and Ronaldo (2, adult)."""
    term.ok("add-book", "0306406152", "Things Fall Apart", "Chinua Achebe",
            "--year", "1958", "--copies", "2")
    term.ok("add-book", "080442957X", "Purple Hibiscus", "Chimamanda Ngozi Adichie")
    term.ok("join", "student", "Amara Okafor", "amara@example.com")
    term.ok("join", "adult", "Ronaldo Mudiwa", "ronaldo@example.com")
    return term


class TestBooks:
    def test_add_book(self, term):
        out = term.ok("add-book", "0306406152", "Things Fall Apart", "Chinua Achebe",
                      "--copies", "2")
        assert "Added book 1" in out and "2 copies" in out
        assert term.library().get_book(1).isbn == "9780306406157"

    def test_one_copy_reads_properly(self, term):
        assert "(1 copy)" in term.ok("add-book", "0306406152", "A", "B")

    def test_bad_isbn(self, term):
        assert "not a valid ISBN" in term.fails("add-book", "123", "A", "B")

    def test_list_and_search(self, ready):
        out = ready.ok("books")
        assert "Things Fall Apart" in out and "Purple Hibiscus" in out
        assert "Purple" not in ready.ok("books", "achebe")
        assert "Things" not in ready.ok("books", "--author", "adichie")
        assert "Purple" not in ready.ok("books", "--to-year", "2000")

    def test_available_only(self, ready):
        ready.ok("lend", "2", "1")
        out = ready.ok("books", "--available")
        assert "Purple" not in out
        assert "2/2" in out

    def test_nothing_found(self, ready):
        assert "No books found." in ready.ok("books", "zzz")

    def test_copies(self, ready):
        assert "owns 5 copies" in ready.ok("copies", "1", "5")
        assert "owns 1 copy" in ready.ok("copies", "978-0-306-40615-7", "1")

    def test_remove_book(self, ready):
        assert "Removed Purple Hibiscus" in ready.ok("remove-book", "080442957X")
        assert "No book" in ready.fails("remove-book", "2")

    def test_book_by_id_or_isbn(self, ready):
        assert "Things Fall Apart" in ready.ok("lend", "9780306406157", "1")
        assert "Purple Hibiscus" in ready.ok("lend", "2", "1")


class TestMembers:
    def test_join_tells_them_their_limits(self, term):
        out = term.ok("join", "child", "Tendai Moyo", "tendai@example.com")
        assert "member number is 1" in out
        assert "3 books for 14 days" in out

    def test_unknown_type_and_duplicate_email(self, ready):
        assert "Unknown member type" in ready.fails("join", "pirate", "Jack", "jack@example.com")
        assert "already exists" in ready.fails("join", "adult", "A", "AMARA@example.com")

    def test_members_table(self, ready):
        out = ready.ok("members")
        assert "Amara Okafor" in out and "student" in out

    def test_suspend_and_reinstate(self, ready):
        assert "suspended" in ready.ok("suspend", "1")
        assert "suspended" in ready.fails("lend", "1", "1")
        assert "active again" in ready.ok("reinstate", "1")
        ready.ok("lend", "1", "1")


class TestLending:
    def test_lend_return_and_renew(self, ready, clock):
        assert "due back on 2026-10-29" in ready.ok("lend", "1", "1")
        clock.advance(10)
        assert "now due on 2026-11-08" in ready.ok("renew", "1")
        assert "Things Fall Apart is back." in ready.ok("return", "1")
        assert ready.library().loans_for(1) == []

    def test_late_return_shows_the_fine(self, ready, clock):
        ready.ok("lend", "1", "2")
        clock.advance(25)
        out = ready.ok("return", "1")
        assert "4 days late" in out
        assert "Fine 1: £1.00" in out

    def test_refused_lend_saves_nothing(self, ready):
        ready.ok("lend", "2", "1")
        assert "out or reserved" in ready.fails("lend", "2", "2")
        assert ready.library().loans_for(2) == []

    def test_loans_and_history(self, ready, clock):
        ready.ok("lend", "1", "1")
        ready.ok("lend", "2", "1")
        ready.ok("return", "1")
        assert "Things" not in ready.ok("loans", "1")
        assert "Things" in ready.ok("loans", "1", "--history")
        assert "No books on loan." in ready.ok("loans", "2")

    def test_loans_mark_late_books(self, ready, clock):
        ready.ok("lend", "1", "2")
        clock.advance(30)
        assert "9 days late" in ready.ok("loans", "2")

    def test_unknown_loan(self, ready):
        assert "No loan" in ready.fails("return", "9")


class TestReservationsAndFines:
    def test_reserve_return_and_collect(self, ready):
        ready.ok("lend", "2", "2")
        assert "number 1 in the queue" in ready.ok("reserve", "2", "1")
        assert "waiting" in ready.ok("reservations", "1")
        out = ready.ok("return", "1")
        assert "Keep it aside for Amara Okafor (#1) until 2026-10-04" in out
        assert "ready" in ready.ok("reservations", "1")
        ready.ok("lend", "2", "1")
        assert "No reservations." in ready.ok("reservations", "1")

    def test_cancel(self, ready):
        ready.ok("lend", "2", "2")
        ready.ok("reserve", "2", "1")
        assert "cancelled" in ready.ok("cancel", "1")
        assert "already cancelled" in ready.fails("cancel", "1")

    def test_fines_and_paying(self, ready, clock):
        ready.ok("lend", "1", "2")
        clock.advance(25)
        ready.ok("return", "1")
        assert "Owed: £1.00" in ready.ok("fines", "2")
        assert "Paid £1.00" in ready.ok("pay", "1")
        assert "Owed: £0.00" in ready.ok("fines", "2")
        assert "already paid" in ready.fails("pay", "1")


class TestReport:
    def test_report_sections(self, ready, clock):
        ready.ok("lend", "1", "2")
        clock.advance(30)
        out = ready.ok("report")
        for title in ("Overdue", "Most borrowed", "Members", "Stock"):
            assert f"=== {title} ===" in out
        assert "Ronaldo Mudiwa" in out
        assert "Total fines owed: £0.00" in out


class TestRunning:
    def test_default_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert main(["books"]) == 0
        assert (tmp_path / "data" / "library.db").exists()
        assert "No books found." in capsys.readouterr().out

    def test_python_dash_m_library(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["library", "--file", str(tmp_path / "l.db"), "members"])
        with pytest.raises(SystemExit) as stopped:
            runpy.run_module("library", run_name="__main__")
        assert stopped.value.code == 0
        assert "No members yet." in capsys.readouterr().out

    def test_damaged_database(self, tmp_path, clock):
        path = tmp_path / "library.db"
        path.write_text("not a database " * 100, encoding="utf-8")
        err = io.StringIO()
        assert LibraryCLI(clock=clock, out=io.StringIO(), err=err).run(
            ["--file", str(path), "books"]) == 1
        assert err.getvalue().startswith("Error: ")

    def test_demo_does_not_make_a_file(self, term):
        out = term.ok("demo")
        assert "Things the library refuses to do" in out
        assert not term.path.exists()

    def test_typing_mistakes_exit_with_2(self, term, capsys):
        for argv in ([], ["lend", "1"], ["return", "one"], ["fly"]):
            with pytest.raises(SystemExit) as stopped:
                term.run(*argv)
            assert stopped.value.code == 2


class TestAddingCommands:
    def test_a_new_command_works_without_editing_the_cli(self, ready):
        class CountCommand(Command):
            name = "count"
            help = "how many books there are"

            def run(self, session: Session, args: argparse.Namespace) -> None:
                session.say(f"{len(session.library.books)} books")

        out = ready.ok("count", commands=[*default_commands(), CountCommand()])
        assert out.strip() == "2 books"

    def test_two_commands_with_one_name(self):
        with pytest.raises(ValueError, match="lend"):
            LibraryCLI(commands=[*default_commands(), default_commands()[8]])

    def test_every_command_has_help(self):
        cli = LibraryCLI()
        assert len(cli.command_names) == len(default_commands())
        assert all(c.name and c.help for c in default_commands())

    def test_session_without_a_library(self):
        session = Session(io.StringIO())
        with pytest.raises(RuntimeError):
            session.library
        with pytest.raises(RuntimeError):
            session.report
