"""Library members. Each kind of member borrows by its own rules.

An adult, a student and a child all borrow books, but how many they can
take and for how long is different. The rest of the library only ever asks
a member "how many?" and "for how long?", and never checks which kind it is.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import TypeVar

from .enums import MemberStatus
from .exceptions import LoanLimitError, MemberNotActiveError, ValidationError
from .validation import clean_email, clean_text, whole_number

_MemberT = TypeVar("_MemberT", bound=type["Member"])
_MEMBER_TYPES: dict[str, type["Member"]] = {}


def register_member_type(member_class: _MemberT) -> _MemberT:
    """Used as @register_member_type above a class so it can be picked by name."""
    name = member_class.MEMBER_TYPE
    if name in _MEMBER_TYPES:
        raise ValueError(f"Member type {name!r} is already used.")
    _MEMBER_TYPES[name] = member_class
    return member_class


def member_class_for(name: str) -> type["Member"]:
    """Find a member class by its name, e.g. "student"."""
    try:
        return _MEMBER_TYPES[name]
    except KeyError:
        allowed = ", ".join(_MEMBER_TYPES)
        raise ValidationError(f"Unknown member type {name!r}. Choose from: {allowed}.") from None


def member_type_names() -> tuple[str, ...]:
    return tuple(_MEMBER_TYPES)


class Member(ABC):
    """Someone with a library card.

    Subclasses say how many books they can borrow and for how many days.
    Everything else, like the name, email and being suspended, is shared.
    """

    MEMBER_TYPE = "member"
    MAX_RENEWALS = 2  # how many times one loan can be extended

    def __init__(
        self,
        name: str,
        email: str,
        joined_on: date | None = None,
        status: MemberStatus = MemberStatus.ACTIVE,
        member_id: int | None = None,
    ) -> None:
        self.name = name
        self.email = email
        if joined_on is not None and not isinstance(joined_on, date):
            raise ValidationError("Joined date must be a date.")
        self._joined_on = joined_on or date.today()
        if not isinstance(status, MemberStatus):
            raise ValidationError("Status must be a MemberStatus.")
        self._status = status
        self._member_id: int | None = None
        if member_id is not None:
            self.assign_id(member_id)

    # ------------------------------------------------------------------
    # What each kind of member must provide
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def max_loans(self) -> int:
        """The most books this member can have out at once."""

    @property
    @abstractmethod
    def loan_days(self) -> int:
        """How many days a book can be kept before it's due back."""

    # ------------------------------------------------------------------
    # Details
    # ------------------------------------------------------------------

    @property
    def member_id(self) -> int | None:
        return self._member_id

    def assign_id(self, member_id: int) -> None:
        """Set by the database when the member is first saved. Only once."""
        if self._member_id is not None:
            raise ValidationError("This member already has an id.")
        self._member_id = whole_number(member_id, "Member id", minimum=1)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = clean_text(value, "Name")

    @property
    def email(self) -> str:
        return self._email

    @email.setter
    def email(self, value: str) -> None:
        self._email = clean_email(value)

    @property
    def joined_on(self) -> date:
        return self._joined_on

    @property
    def status(self) -> MemberStatus:
        return self._status

    @property
    def is_active(self) -> bool:
        return self._status is MemberStatus.ACTIVE

    # ------------------------------------------------------------------
    # Borrowing rules
    # ------------------------------------------------------------------

    def due_date(self, borrowed_on: date) -> date:
        return borrowed_on + timedelta(days=self.loan_days)

    def can_borrow_more(self, books_on_loan: int) -> bool:
        return self.is_active and books_on_loan < self.max_loans

    def check_can_borrow(self, books_on_loan: int) -> None:
        """Raise if this member can't take one more book right now."""
        if not self.is_active:
            raise MemberNotActiveError(f"{self.name}'s card is suspended.")
        if books_on_loan >= self.max_loans:
            raise LoanLimitError(
                f"{self.name} already has {books_on_loan} books. "
                f"The limit for a {self.MEMBER_TYPE} member is {self.max_loans}."
            )

    def suspend(self) -> None:
        self._status = MemberStatus.SUSPENDED

    def reinstate(self) -> None:
        self._status = MemberStatus.ACTIVE

    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        """Emails are unique, so two members with the same email are the same person."""
        if not isinstance(other, Member):
            return NotImplemented
        return self._email == other._email

    def __hash__(self) -> int:
        return hash(self._email)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._name!r}, {self._email!r}, member_id={self._member_id})"

    def __str__(self) -> str:
        number = f" (#{self._member_id})" if self._member_id else ""
        return f"{self._name}{number}"


@register_member_type
class AdultMember(Member):
    """The standard card."""

    MEMBER_TYPE = "adult"

    @property
    def max_loans(self) -> int:
        return 5

    @property
    def loan_days(self) -> int:
        return 21


@register_member_type
class StudentMember(Member):
    """More books for longer, because of coursework."""

    MEMBER_TYPE = "student"

    @property
    def max_loans(self) -> int:
        return 8

    @property
    def loan_days(self) -> int:
        return 28


@register_member_type
class ChildMember(Member):
    """Fewer books and a shorter loan, so books come back sooner."""

    MEMBER_TYPE = "child"
    MAX_RENEWALS = 1

    @property
    def max_loans(self) -> int:
        return 3

    @property
    def loan_days(self) -> int:
        return 14
