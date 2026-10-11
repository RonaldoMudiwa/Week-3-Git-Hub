"""Helpers for amounts of money. Always Decimal, never float, so pennies add up."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .exceptions import ValidationError

PENNY = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value: Decimal | int | str) -> Decimal:
    """Turn "0.25", 2 or Decimal("0.25") into an amount rounded to the penny."""
    if isinstance(value, (bool, float)) or value is None:
        raise ValidationError("Use text, a whole number or Decimal for money.")
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValidationError(f"{value!r} is not a valid amount.") from None
    if not amount.is_finite():
        raise ValidationError("Amount must be a real number.")
    return amount.quantize(PENNY, rounding=ROUND_HALF_UP)


def format_money(amount: Decimal) -> str:
    """£1,234.56"""
    sign = "-" if amount < 0 else ""
    return f"{sign}£{abs(amount):,.2f}"
