"""Tests for importing and exporting books as CSV."""

from __future__ import annotations

import csv

import pytest

from library import BookExporter, BookImporter, DuplicateError, ValidationError


def write(path, text: str, encoding: str = "utf-8"):
    path.write_text(text, encoding=encoding)
    return path


GOOD = """isbn,title,author,year,copies
0306406152,Things Fall Apart,Chinua Achebe,1958,2
080442957X,Purple Hibiscus,Chimamanda Ngozi Adichie,,
"""


class TestImport:
    def test_adds_every_book(self, library, tmp_path):
        result = BookImporter(library).import_file(write(tmp_path / "b.csv", GOOD))
        assert [b.title for b in result.added] == ["Things Fall Apart", "Purple Hibiscus"]
        assert library.find_book("0306406152").copies == 2
        purple = library.find_book("080442957X")
        assert (purple.year, purple.copies) == (None, 1)

    def test_headings_in_any_case_and_excel_bom(self, library, tmp_path):
        text = "﻿ISBN,Title,AUTHOR\n0306406152,Things Fall Apart,Chinua Achebe\n"
        BookImporter(library).import_file(write(tmp_path / "b.csv", text))
        assert library.has_book("9780306406157")

    def test_a_bad_line_stops_everything(self, library, tmp_path):
        text = GOOD + "123,Bad,Book,,\n"
        with pytest.raises(ValidationError, match="Line 4"):
            BookImporter(library).import_file(write(tmp_path / "b.csv", text))
        assert library.books == []

    def test_book_already_in_the_catalogue(self, library, tmp_path):
        library.add_book("0306406152", "Things Fall Apart", "Chinua Achebe")
        path = write(tmp_path / "b.csv", GOOD)
        with pytest.raises(DuplicateError, match="Line 2"):
            BookImporter(library).import_file(path)
        assert len(library.books) == 1   # Purple Hibiscus wasn't half added

        result = BookImporter(library).import_file(path, skip_existing=True)
        assert result.skipped == ("9780306406157",)
        assert len(result.added) == 1

    def test_same_book_twice_in_one_file(self, library, tmp_path):
        text = GOOD + "978-0-306-40615-7,Again,Someone,,\n"
        with pytest.raises(ValidationError, match="twice"):
            BookImporter(library).import_file(write(tmp_path / "b.csv", text))

    @pytest.mark.parametrize("text, message", [
        ("isbn,title\n0306406152,Things\n", "missing the column"),
        ("isbn,title,author\n", "no books"),
        ("", "no books"),
        ("isbn,title,author,year\n0306406152,A,B,nineteen\n", "Year should be a whole number"),
        ("isbn,title,author,copies\n0306406152,A,B,0\n", "Line 2"),
    ])
    def test_problems_in_the_file(self, library, tmp_path, text, message):
        with pytest.raises(ValidationError, match=message):
            BookImporter(library).import_file(write(tmp_path / "b.csv", text))

    def test_missing_file(self, library, tmp_path):
        with pytest.raises(ValidationError, match="Could not read"):
            BookImporter(library).import_file(tmp_path / "nope.csv")

    def test_file_that_is_not_utf8(self, library, tmp_path):
        path = tmp_path / "b.csv"
        path.write_bytes(b"isbn,title,author\n0306406152,Caf\xe9,B\n")
        with pytest.raises(ValidationError, match="UTF-8"):
            BookImporter(library).import_file(path)


class TestExport:
    def test_round_trip(self, stocked, tmp_path):
        stocked.lend(1, 1)
        path = tmp_path / "out" / "books.csv"
        assert BookExporter(stocked).export_file(path) == 2
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        achebe = next(r for r in rows if r["isbn"] == "9780306406157")
        assert (achebe["copies"], achebe["on_shelf"]) == ("2", "1")

    def test_exported_file_can_be_imported(self, stocked, library, tmp_path, db, clock):
        from library import Database, Library

        path = tmp_path / "books.csv"
        BookExporter(stocked).export_file(path)
        with Database() as other_db:
            other = Library.open(other_db, clock)
            assert len(BookImporter(other).import_file(path).added) == 2

    def test_cannot_write(self, stocked, tmp_path):
        with pytest.raises(ValidationError, match="Could not write"):
            BookExporter(stocked).export_file(tmp_path)   # a folder, not a file
