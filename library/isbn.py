"""ISBNs: the number printed above the barcode on every book.

Old books have a 10 digit ISBN and newer ones have 13 digits. We store every
book by its 13 digit ISBN, so the same book can't be added twice just
because it was typed in the other format.
"""

from __future__ import annotations

from .exceptions import ValidationError


def normalise_isbn(value: object) -> str:
    """Return the 13 digit ISBN for any valid 10 or 13 digit ISBN.

    Dashes and spaces are ignored, so "978-0-306-40615-7" works.

        >>> normalise_isbn("0-306-40615-2")
        '9780306406157'

    Raises:
        ValidationError: If it's the wrong length or the check digit is wrong.
    """
    if not isinstance(value, str):
        raise ValidationError("ISBN must be text.")
    digits = value.replace("-", "").replace(" ", "").upper()

    if len(digits) == 10:
        if not _is_valid_isbn10(digits):
            raise ValidationError(f"{value!r} is not a valid ISBN. The last digit doesn't match.")
        first_twelve = "978" + digits[:9]
        return first_twelve + _isbn13_check_digit(first_twelve)

    if len(digits) == 13:
        if not digits.isdigit() or _isbn13_check_digit(digits[:12]) != digits[12]:
            raise ValidationError(f"{value!r} is not a valid ISBN. The last digit doesn't match.")
        return digits

    raise ValidationError(f"{value!r} is not a valid ISBN. It should have 10 or 13 digits.")


def _isbn13_check_digit(first_twelve: str) -> str:
    # Digits are weighted 1, 3, 1, 3... and the total must end in 0.
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first_twelve))
    return str((10 - total % 10) % 10)


def _is_valid_isbn10(digits: str) -> bool:
    # The last character can be X, which means 10.
    if not digits[:9].isdigit() or not (digits[9].isdigit() or digits[9] == "X"):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
    return total % 11 == 0
