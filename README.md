# Library Management System

A library you run from the terminal, written in Python. Books, members and
loans are saved in a SQLite database.

Project 3 of a 12 week portfolio. Week 1 used the four OOP principles and
Week 2 added SOLID. This week adds a real database.

## Status

Day 6 of 7. Books with ISBN checking, three kinds of member that each
borrow by their own rules, everything saved in SQLite, lending, returns and
renewals, reservations, late fines, search, reports and a command line
interface.

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate           # macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt  # only needed for the tests

python -m library --help         # see every command
python -m library demo           # a quick tour with made up members
pytest                           # run the tests
```

Needs Python 3.10 or newer. The app itself only uses the standard library.

## Using it from the terminal

Everything is saved in `data/library.db`, which is made the first time you
run a command. Use `--file other.db` before the command for a separate
library.

```bash
python -m library add-book 0306406152 "Things Fall Apart" "Chinua Achebe" --year 1958 --copies 2
python -m library join student "Amara Okafor" amara@example.com

python -m library books achebe --available    # search, only books on the shelf
python -m library lend 1 1                    # book id or ISBN, then member number
python -m library renew 1
python -m library return 1                    # shows any fine, and who to keep it for

python -m library reserve 1 2
python -m library loans 1 --history
python -m library fines 2
python -m library pay 1
python -m library report                      # late books, popular books, members, stock
```

If the library says no, it prints `Error: ...` and nothing changes, because
every command runs inside one database transaction. Each command is its own
small class in `cli.py`, so adding one never means changing the others.

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

| Type | Books at once | Loan length | Renewals | Late fine |
| --- | --- | --- | --- | --- |
| `AdultMember` | 5 | 21 days | 2 | 25p a day, up to £10 |
| `StudentMember` | 8 | 28 days | 2 | 15p a day, up to £5 |
| `ChildMember` | 3 | 14 days | 1 | None |

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

## Reservations

When every copy is out, a member can join the queue for it.

```python
reservation = library.reserve(book_id, member_id)
receipt = library.give_back(loan_id)
receipt.held_for          # the first person in the queue now has a copy kept
library.lend(book_id, that_member_id)    # they collect it
```

When a copy comes back and someone is waiting, it's kept on the shelf for
the first person in line for 3 days. Nobody else can borrow it. If they don't
collect it in time, it moves to the next person, or back onto the shelf if
nobody else is waiting. Copies the library buys later go to the queue first
too. A book with people waiting can't be renewed. A reservation can be
cancelled, and a kept copy then moves on.

## Late fines

Each member type has a `FinePolicy`. `DailyFine("0.25", maximum="10")`
charges by the day up to a limit, and `NoFine()` charges nothing. When a late
book comes back, `give_back()` works out the fine from the member's own
policy and saves it.

```python
receipt = library.give_back(loan_id)
receipt.fine                       # Fine(£1.00 for loan 4, unpaid) or None
library.amount_owed(member_id)     # Decimal('1.00')
library.pay_fine(receipt.fine.fine_id)
```

Owing £5 or more stops a member borrowing until they pay. Money is a
`Decimal` and is saved as text, so no pennies are lost to rounding.

## Search

```python
library.search("achebe")                         # title or author, any case
library.search(author="adichie", year_from=2000)
library.search("sun", available_only=True)        # only books on the shelf now
```

Every part given must match. The search is turned into one SQL query with
`?` placeholders. `%` and `_` are wildcards in SQL's `LIKE`, so they're
escaped first. That way searching for `100%` finds "100%", not everything
starting with 100.

## Reports

```python
from library import LibraryReport, TextFormatter

report = LibraryReport(db)
fmt = TextFormatter()

print(fmt.overdue(report.overdue()))          # late books and who has them
print(fmt.popular(report.most_borrowed()))    # most lent books
print(fmt.members(report.members()))          # books out and money owed per member
print(fmt.stock(report.stock()))              # copies owned, out, kept and on the shelf
```

These questions need several tables at once, so `LibraryReport` uses SQL
`JOIN`, `GROUP BY` and `COUNT` instead of loading every loan into Python.
Money is the one thing added up in Python, because SQLite would turn the
amounts into floats. `LibraryReport` only works out the numbers and
`TextFormatter` only prints them.

## Tests

```bash
pytest          # 280 tests
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
