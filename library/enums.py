"""Fixed lists of choices used across the package."""

from __future__ import annotations

from enum import Enum, unique


@unique
class MemberStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"  # can't borrow until reinstated, e.g. a lost book


@unique
class ReservationStatus(Enum):
    WAITING = "waiting"      # in the queue
    READY = "ready"          # a copy is being kept for them
    COLLECTED = "collected"  # they borrowed it
    CANCELLED = "cancelled"
    EXPIRED = "expired"      # they didn't collect it in time
