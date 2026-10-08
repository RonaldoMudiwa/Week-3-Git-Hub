"""Fixed lists of choices used across the package."""

from __future__ import annotations

from enum import Enum, unique


@unique
class MemberStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"  # can't borrow until reinstated, e.g. a lost book
