# Library Management System

A library you run from the terminal, written in Python. Books, members and
loans are saved in a SQLite database.

Project 3 of a 12 week portfolio. Week 1 used the four OOP principles and
Week 2 added SOLID. This week adds a real database.

## Status

Day 1 of 7. Books with ISBN checking, and three kinds of member that each
borrow by their own rules.

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate           # macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt  # only needed for the tests

pytest                           # run the tests
```

Needs Python 3.10 or newer. The app itself only uses the standard library.

## Books

```python
from library import Book

book = Book("0-306-40615-2", "Things Fall Apart", "Chinua Achebe", 1958, copies=2)
book.isbn                     # '9780306406157'
more = book.with_changes(copies=3)
```

Every ISBN is checked and turned into the 13 digit form, so the same book
typed as `0306406152` or `978-0-306-40615-7` is stored the same way. A `Book`
can't be edited in place. `with_changes()` gives a new one and runs all the
checks again.

## Members

| Type | Books at once | Loan length | Renewals |
| --- | --- | --- | --- |
| `AdultMember` | 5 | 21 days | 2 |
| `StudentMember` | 8 | 28 days | 2 |
| `ChildMember` | 3 | 14 days | 1 |

```python
from library import member_class_for

member = member_class_for("student")("Amara Okafor", "amara@example.com")
member.due_date(date(2026, 10, 1))    # 2026-10-29
member.check_can_borrow(books_on_loan=8)   # raises LoanLimitError
```

`Member` is an abstract class. Each type only says how many books and for how
long. A new type is a new subclass with `@register_member_type` above it.

## Tests

```bash
pytest          # 74 tests
```

## Week plan

| Day | Focus |
| --- | --- |
| 1 | Books, ISBNs and member types |
| 2 | Saving books and members in SQLite |
| 3 | Lending, returns and renewals |
| 4 | Reservations and late fines |
| 5 | Search and reports |
| 6 | Command line interface |
| 7 | CSV import, final tests and README |
