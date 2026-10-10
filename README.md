# Library Management System

A library you run from the terminal, written in Python. Books, members and
loans are saved in a SQLite database.

Project 3 of a 12 week portfolio. Week 1 used the four OOP principles and
Week 2 added SOLID. This week adds a real database.

## Status

Day 3 of 7. Books with ISBN checking, three kinds of member that each
borrow by their own rules, everything saved in SQLite, and lending, returns
and renewals.

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

## The database

```python
from library import Database, SQLiteBookRepository, SQLiteMemberRepository

with Database("data/library.db") as db:      # or Database() for one in memory
    books = SQLiteBookRepository(db)
    members = SQLiteMemberRepository(db)

    book = books.add(Book("0306406152", "Things Fall Apart", "Chinua Achebe"))
    book.book_id                              # 1
    books.find_by_isbn("978-0-306-40615-7")   # the same book

    amara = members.add(member_class_for("student")("Amara Okafor", "amara@example.com"))
    members.get(amara.member_id)              # comes back as a StudentMember
```

- **Tables are set up for you.** Each change to the tables is a numbered
  step in `MIGRATIONS`. The database remembers which step it's on, so an
  old file is brought up to date when it's opened, and a file from a newer
  version of the program is refused instead of being damaged.
- **Values never go into the SQL text.** Every query uses `?` placeholders,
  so a title like `Bobby'); DROP TABLE books` is stored as a title. This
  stops SQL injection.
- **Transactions.** `with db.transaction():` makes a group of changes happen
  together or not at all. If anything inside fails, everything is undone.
- **Unique rules live in the database too.** ISBNs and emails are `UNIQUE`
  columns, so even a bug in the Python can't save the same book twice.
- **Repositories.** The rest of the program only knows `BookRepository` and
  `MemberRepository`, which are abstract. The SQLite versions plug in behind
  them.

## Lending

`Library` is the front desk. It's the one place that knows the rules that
involve a book, a member and their loans all at once.

```python
from library import Database, Library

with Database("data/library.db") as db:
    library = Library.open(db)

    book = library.add_book("0306406152", "Things Fall Apart", "Chinua Achebe", copies=2)
    amara = library.register_member("student", "Amara Okafor", "amara@example.com")

    loan = library.lend(book.book_id, amara.member_id)   # due in 28 days for a student
    library.available_copies(book.book_id)               # 1
    library.renew(loan.loan_id)                          # another 28 days from today
    library.give_back(loan.loan_id)
```

A book can't be lent if:

- the member is suspended
- they have a late book (it has to come back first)
- they're at the limit for their type of card
- they already have a copy of that book
- every copy is out

Each of these has its own error, and they all inherit from `LoanError`, so
`except LoanError` catches any of them. The checks and the new loan run in
one transaction, so two people can never both get the last copy.

A loan can be renewed while it's not late, up to the limit for the member's
card. The new due date counts from the day it's renewed. A book that has
ever been lent can't be deleted, so no one's history points at a missing
book. Database rules (`FOREIGN KEY ... ON DELETE RESTRICT`) back this up.

`Library` only uses the abstract repositories, and is handed the database's
`transaction` function, so it never touches SQLite directly.

## Tests

```bash
pytest          # 156 tests
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
