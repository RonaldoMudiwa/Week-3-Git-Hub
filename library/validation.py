"""Small checks shared by books and members."""

from __future__ import annotations

import re

from .exceptions import ValidationError

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_text(value: object, field_name: str) -> str:
    """Strip spaces from the ends. Blank text isn't allowed."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} can't be blank.")
    return value.strip()


def clean_email(value: object) -> str:
    """Check the email looks right and lower-case it, so case never matters."""
    email = clean_text(value, "Email").lower()
    if not EMAIL_PATTERN.match(email):
        raise ValidationError(f"{email!r} doesn't look like an email address.")
    return email


def whole_number(value: object, field_name: str, minimum: int = 0) -> int:
    """A real int at or above the minimum. True and False don't count."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field_name} must be a whole number.")
    if value < minimum:
        raise ValidationError(f"{field_name} must be at least {minimum}, got {value}.")
    return value
