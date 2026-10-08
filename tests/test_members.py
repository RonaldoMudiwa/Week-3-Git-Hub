"""Tests for members.

The first group runs on every member type, because the rest of the library
treats them all the same way.
"""

from __future__ import annotations

from datetime import date

import pytest

from library import (
    AdultMember,
    ChildMember,
    LoanLimitError,
    Member,
    MemberNotActiveError,
    MemberStatus,
    StudentMember,
    ValidationError,
    member_class_for,
    member_type_names,
    register_member_type,
)

ALL_TYPES = [AdultMember, StudentMember, ChildMember]


@pytest.fixture(params=ALL_TYPES, ids=lambda cls: cls.MEMBER_TYPE)
def member(request) -> Member:
    return request.param("Amara Okafor", "Amara@Example.com", joined_on=date(2026, 9, 1))


class TestEveryMemberType:
    def test_details(self, member):
        assert member.name == "Amara Okafor"
        assert member.email == "amara@example.com"
        assert member.joined_on == date(2026, 9, 1)
        assert member.is_active
        assert member.member_id is None

    def test_limits_are_sensible(self, member):
        assert member.max_loans >= 1
        assert member.loan_days >= 7
        assert member.MAX_RENEWALS >= 0

    def test_due_date(self, member):
        borrowed = date(2026, 10, 1)
        assert (member.due_date(borrowed) - borrowed).days == member.loan_days

    def test_can_borrow_up_to_the_limit(self, member):
        member.check_can_borrow(member.max_loans - 1)
        assert member.can_borrow_more(member.max_loans - 1)
        assert not member.can_borrow_more(member.max_loans)
        with pytest.raises(LoanLimitError):
            member.check_can_borrow(member.max_loans)

    def test_suspended_member_cannot_borrow(self, member):
        member.suspend()
        assert member.status is MemberStatus.SUSPENDED
        assert not member.can_borrow_more(0)
        with pytest.raises(MemberNotActiveError):
            member.check_can_borrow(0)
        member.reinstate()
        member.check_can_borrow(0)

    def test_id_can_only_be_set_once(self, member):
        member.assign_id(7)
        assert member.member_id == 7
        with pytest.raises(ValidationError):
            member.assign_id(8)

    def test_found_by_its_type_name(self, member):
        assert member_class_for(member.MEMBER_TYPE) is type(member)


@pytest.mark.parametrize("cls, loans, days", [
    (AdultMember, 5, 21),
    (StudentMember, 8, 28),
    (ChildMember, 3, 14),
])
def test_each_type_has_its_own_rules(cls, loans, days):
    member = cls("Ronaldo", "r@example.com")
    assert member.max_loans == loans
    assert member.loan_days == days


def test_children_renew_less():
    assert ChildMember.MAX_RENEWALS < AdultMember.MAX_RENEWALS


def test_joined_defaults_to_today():
    assert AdultMember("Ronaldo", "r@example.com").joined_on == date.today()


@pytest.mark.parametrize("kwargs", [
    {"name": "", "email": "r@example.com"},
    {"name": "Ronaldo", "email": "not-an-email"},
    {"name": "Ronaldo", "email": "r@example.com", "joined_on": "2026-10-01"},
    {"name": "Ronaldo", "email": "r@example.com", "status": "active"},
    {"name": "Ronaldo", "email": "r@example.com", "member_id": 0},
])
def test_bad_details_are_refused(kwargs):
    with pytest.raises(ValidationError):
        AdultMember(**kwargs)


def test_changing_email_is_checked():
    member = AdultMember("Ronaldo", "r@example.com")
    member.email = "NEW@example.com"
    assert member.email == "new@example.com"
    with pytest.raises(ValidationError):
        member.email = "nope"


def test_member_cannot_be_created_on_its_own():
    with pytest.raises(TypeError):
        Member("Ronaldo", "r@example.com")


def test_same_email_means_same_member():
    assert AdultMember("Ronaldo", "r@example.com") == StudentMember("Ron", "R@example.com")
    assert len({AdultMember("A", "a@example.com"), AdultMember("B", "a@example.com")}) == 1
    assert AdultMember("Ronaldo", "r@example.com") != "r@example.com"


def test_str_and_repr():
    member = AdultMember("Ronaldo", "r@example.com", member_id=3)
    assert str(member) == "Ronaldo (#3)"
    assert str(AdultMember("Ronaldo", "r@example.com")) == "Ronaldo"
    assert repr(member) == "AdultMember('Ronaldo', 'r@example.com', member_id=3)"


def test_unknown_type_name():
    with pytest.raises(ValidationError, match="adult, student, child"):
        member_class_for("pirate")


def test_type_names():
    assert member_type_names()[:3] == ("adult", "student", "child")


def test_new_member_type_can_be_added():
    @register_member_type
    class StaffMember(Member):
        MEMBER_TYPE = "staff_test"

        @property
        def max_loans(self) -> int:
            return 20

        @property
        def loan_days(self) -> int:
            return 60

    staff = member_class_for("staff_test")("Ms Lee", "lee@example.com")
    assert staff.max_loans == 20


def test_type_names_must_be_unique():
    with pytest.raises(ValueError, match="already used"):
        @register_member_type
        class Copy(AdultMember):
            pass
