"""BIN / IIN validation (12-digit identifiers of the Republic of Kazakhstan).

Checksum: weighted sum of the first 11 digits mod 11 with weights 1..11; if the result is 10,
recompute with weights 3..11,1,2; a second 10 means the number is never issued. The result
must equal the 12th digit.

In a BIN the 5th digit is the entity type: 4 resident legal entity, 5 non-resident legal
entity, 6 joint entrepreneurship. In an IIN (a person) the 7th digit encodes century and sex
(1-6) and the first six digits are a birth date.
"""

from __future__ import annotations

import re
from typing import Literal

_DIGITS = re.compile(r"^\d{12}$")
_W1 = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
_W2 = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)

EntityType = Literal["resident_legal_entity", "non_resident_legal_entity", "joint_entrepreneurship"]
_ENTITY_TYPES: dict[str, EntityType] = {
    "4": "resident_legal_entity",
    "5": "non_resident_legal_entity",
    "6": "joint_entrepreneurship",
}


class InvalidBinError(ValueError):
    pass


def checksum(first11: str) -> int | None:
    """Control digit for 11 digits, or None if no valid control digit exists."""
    digits = [int(c) for c in first11]
    for weights in (_W1, _W2):
        control = sum(d * w for d, w in zip(digits, weights, strict=True)) % 11
        if control != 10:
            return control
    return None


def is_valid_checksum(number: str) -> bool:
    return bool(_DIGITS.match(number)) and checksum(number[:11]) == int(number[11])


def validate_bin(value: str) -> tuple[str, EntityType]:
    """Normalize and validate a BIN; returns (bin, entity type). Raises InvalidBinError
    with a message that is safe to show to the client."""
    number = re.sub(r"[\s-]", "", value)
    if not _DIGITS.match(number):
        raise InvalidBinError("BIN must be exactly 12 digits")
    if not is_valid_checksum(number):
        raise InvalidBinError("BIN checksum is invalid (check for a typo)")
    entity = _ENTITY_TYPES.get(number[4])
    if entity is None:
        raise InvalidBinError(
            "This is not a BIN of a legal entity (5th digit must be 4, 5 or 6); "
            "lookups of individuals (IIN) are not supported"
        )
    return number, entity
