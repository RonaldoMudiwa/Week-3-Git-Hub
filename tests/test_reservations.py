"""Tests for reserving books that are all out."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from library import (
    MemberNotActiveError,
    NoCopiesAvailableError,
    RenewalError,
    Reservation,
    ReservationError,
    ReservationNotFoundError,
    ReservationStatus,
    SQLiteReservationRepository,
    ValidationError,
)

ADULT, STUDENT, CHILD = 1, 2, 3
ACHEBE, ADICHIE = 1, 2   # Achebe has 2 copies, Adichie has 1


@pytest.fixture
def busy(stocked):
    """Purple Hibiscus (one copy) is lent to the adult."""
    stocked.loan_out = stocked.lend(ADICHIE, ADULT)
    return stocked


class TestReserving:
    def test_join_the_queue(self, busy, clock):
        reservation = busy.reserve(ADICHIE, STUDENT)
        assert reservation.status is ReservationStatus.WAITING
        assert reservation.reserved_on == clock.today
        assert busy.queue_for(ADICHIE) == [reservation]
        assert busy.reservations_for(STUDENT) == [reservation]

    def test_cannot_reserve_when_a_copy_is_free(self, stocked):
        with pytest.raises(ReservationError, match="on the shelf"):
            stocked.reserve(ACHEBE, STUDENT)

    def test_cannot_reserve_twice(self, busy):
        busy.reserve(ADICHIE, STUDENT)
        with pytest.raises(ReservationError, match="already reserved"):
            busy.reserve(ADICHIE, STUDENT)

    def test_cannot_reserve_a_book_you_have(self, busy):
        with pytest.raises(ReservationError, match="already has"):
            busy.reserve(ADICHIE, ADULT)

    def test_suspended_member_cannot_reserve(self, busy):
        busy.suspend_member(STUDENT)
        with pytest.raises(MemberNotActiveError):
            busy.reserve(ADICHIE, STUDENT)

    def test_queue_is_first_come_first_served(self, busy, clock):
        first = busy.reserve(ADICHIE, STUDENT)
        clock.advance(1)
        second = busy.reserve(ADICHIE, CHILD)
        assert busy.queue_for(ADICHIE) == [first, second]


class TestWhenTheBookComesBack:
    def test_copy_is_kept_for_the_first_in_line(self, busy, clock):
        busy.reserve(ADICHIE, STUDENT)
        busy.reserve(ADICHIE, CHILD)
        receipt = busy.give_back(busy.loan_out.loan_id)
        assert receipt.held_for.member_id == STUDENT
        assert receipt.held_for.status is ReservationStatus.READY
        assert receipt.held_for.expires_on == date(2026, 10, 4)
        assert busy.available_copies(ADICHIE) == 0
        assert [r.member_id for r in busy.queue_for(ADICHIE)] == [CHILD]

    def test_others_cannot_take_the_kept_copy(self, busy):
        busy.reserve(ADICHIE, STUDENT)
        busy.give_back(busy.loan_out.loan_id)
        with pytest.raises(NoCopiesAvailableError, match="reserved"):
            busy.lend(ADICHIE, CHILD)

    def test_the_reserver_collects_it(self, busy):
        reservation = busy.reserve(ADICHIE, STUDENT)
        busy.give_back(busy.loan_out.loan_id)
        loan = busy.lend(ADICHIE, STUDENT)
        assert loan.member_id == STUDENT
        assert busy.reservations_for(STUDENT) == []
        assert busy.get_reservation(reservation.reservation_id).status is \
            ReservationStatus.COLLECTED

    def test_no_queue_means_the_copy_goes_back_on_the_shelf(self, busy):
        receipt = busy.give_back(busy.loan_out.loan_id)
        assert receipt.held_for is None
        assert busy.available_copies(ADICHIE) == 1

    def test_uncollected_copy_passes_to_the_next_person(self, busy, clock):
        first = busy.reserve(ADICHIE, STUDENT)
        busy.reserve(ADICHIE, CHILD)
        busy.give_back(busy.loan_out.loan_id)
        clock.advance(4)   # one day past the 3 day hold
        expired = busy.process_expired_holds()
        assert [r.reservation_id for r in expired] == [first.reservation_id]
        child_hold = busy.reservations_for(CHILD)[0]
        assert child_hold.status is ReservationStatus.READY
        assert child_hold.expires_on == clock.today + timedelta(days=3)
        assert busy.reservations_for(STUDENT) == []

    def test_expired_hold_with_nobody_waiting_frees_the_copy(self, busy, clock):
        busy.reserve(ADICHIE, STUDENT)
        busy.give_back(busy.loan_out.loan_id)
        clock.advance(4)
        # Lending tidies old holds first, so anyone can now take it.
        busy.lend(ADICHIE, CHILD)

    def test_hold_still_valid_on_its_last_day(self, busy, clock):
        busy.reserve(ADICHIE, STUDENT)
        busy.give_back(busy.loan_out.loan_id)
        clock.advance(3)
        assert busy.process_expired_holds() == []
        busy.lend(ADICHIE, STUDENT)

    def test_new_copies_go_to_the_queue_first(self, busy):
        busy.reserve(ADICHIE, STUDENT)
        busy.set_copies(ADICHIE, 2)
        assert busy.reservations_for(STUDENT)[0].status is ReservationStatus.READY
        assert busy.available_copies(ADICHIE) == 0


class TestCancelling:
    def test_cancel_a_waiting_reservation(self, busy):
        reservation = busy.reserve(ADICHIE, STUDENT)
        assert busy.cancel_reservation(reservation.reservation_id).status is \
            ReservationStatus.CANCELLED
        assert busy.queue_for(ADICHIE) == []

    def test_cancelling_a_kept_copy_passes_it_on(self, busy):
        first = busy.reserve(ADICHIE, STUDENT)
        busy.reserve(ADICHIE, CHILD)
        busy.give_back(busy.loan_out.loan_id)
        busy.cancel_reservation(first.reservation_id)
        assert busy.reservations_for(CHILD)[0].status is ReservationStatus.READY

    def test_cannot_cancel_twice(self, busy):
        reservation = busy.reserve(ADICHIE, STUDENT)
        busy.cancel_reservation(reservation.reservation_id)
        with pytest.raises(ReservationError, match="cancelled"):
            busy.cancel_reservation(reservation.reservation_id)

    def test_missing_reservation(self, busy):
        with pytest.raises(ReservationNotFoundError):
            busy.cancel_reservation(77)


def test_book_with_a_queue_cannot_be_renewed(busy):
    busy.reserve(ADICHIE, STUDENT)
    with pytest.raises(RenewalError, match="reserved"):
        busy.renew(busy.loan_out.loan_id)


class TestReservationRecord:
    def test_ready_needs_an_expiry_date(self):
        with pytest.raises(ValidationError):
            Reservation(1, 1, date(2026, 10, 1), ReservationStatus.READY)

    @pytest.mark.parametrize("kwargs", [
        {"book_id": 0}, {"reserved_on": "2026-10-01"}, {"status": "waiting"},
    ])
    def test_bad_values(self, kwargs):
        details = {"book_id": 1, "member_id": 1, "reserved_on": date(2026, 10, 1)}
        details.update(kwargs)
        with pytest.raises(ValidationError):
            Reservation(**details)

    def test_is_held(self):
        ready = Reservation(1, 1, date(2026, 10, 1), ReservationStatus.READY, date(2026, 10, 4))
        assert ready.is_held(date(2026, 10, 4))
        assert not ready.is_held(date(2026, 10, 5))
        assert not Reservation(1, 1, date(2026, 10, 1)).is_held(date(2026, 10, 1))


class TestReservationRepository:
    def test_errors(self, stocked, db):
        repo = SQLiteReservationRepository(db)
        with pytest.raises(ValidationError):
            repo.add(Reservation(99, 1, date(2026, 10, 1)))
        saved = repo.add(Reservation(1, 1, date(2026, 10, 1)))
        with pytest.raises(ValidationError):
            repo.add(saved)
        with pytest.raises(ValidationError):
            repo.update(Reservation(1, 1, date(2026, 10, 1)))
        with pytest.raises(ReservationNotFoundError):
            repo.update(Reservation(1, 1, date(2026, 10, 1), reservation_id=50))
