"""
validators.py - Server-side validation and normalisation.

Pure functions only (no database access), so they are easy to unit-test.

Normalisation is intentionally GENTLE:
* student_id  -> trimmed and UPPER-cased        ("  cs2024001 " -> "CS2024001")
* email       -> trimmed and lower-cased        (" Ana@Uni.EDU" -> "ana@uni.edu")
* full_name   -> trimmed, repeated spaces collapsed, CASE PRESERVED
                 ("  ananya   Sharma " -> "ananya Sharma")
* department  -> trimmed and matched to the official list
We never re-capitalise, transliterate or otherwise "fix" a person's name,
because that could change its meaning (e.g. "McDonald", "de la Cruz").
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Mapping

FIELD_LABELS = {
    "student_id": "Student ID",
    "full_name": "Full name",
    "email": "Email address",
    "department": "Department",
}

MAX_LENGTHS = {"student_id": 20, "full_name": 100, "email": 254, "department": 100}

# Practical email pattern: local@domain.tld (no spaces, at least one dot in domain).
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)

NAME_ALLOWED_PUNCTUATION = set(" '-.")


@dataclass
class ValidationResult:
    cleaned: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalize_student_id(value: str) -> str:
    return value.strip().upper()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_name(value: str) -> str:
    return collapse_whitespace(value)


def make_name_key(value: str) -> str:
    """Comparison key for names: Unicode-normalised and case-folded.
    Used for search and similarity only - never displayed."""
    return unicodedata.normalize("NFKC", collapse_whitespace(value)).casefold()


def _as_text(value) -> str:
    if value is None:
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def validate_student(
    raw: Mapping,
    student_id_pattern: str = r"^[A-Z]{2,4}[0-9]{3,8}$",
    departments: Iterable[str] | None = None,
    student_id_example: str = "CS2024001",
) -> ValidationResult:
    """Validate and normalise a submitted student record.

    Returns a ValidationResult whose ``cleaned`` dict contains the normalised
    values and whose ``errors`` dict maps field name -> friendly message.
    """
    result = ValidationResult()

    student_id = normalize_student_id(_as_text(raw.get("student_id")))
    full_name = normalize_name(_as_text(raw.get("full_name")))
    email = normalize_email(_as_text(raw.get("email")))
    department = collapse_whitespace(_as_text(raw.get("department")))

    values = {
        "student_id": student_id,
        "full_name": full_name,
        "email": email,
        "department": department,
    }

    # 1. Required fields + length limits
    for name, value in values.items():
        if not value:
            result.errors[name] = f"{FIELD_LABELS[name]} is required."
        elif len(value) > MAX_LENGTHS[name]:
            result.errors[name] = (
                f"{FIELD_LABELS[name]} must be at most {MAX_LENGTHS[name]} characters."
            )

    # 2. Student ID format
    if "student_id" not in result.errors and not re.fullmatch(student_id_pattern, student_id):
        result.errors["student_id"] = (
            "Student ID format is invalid. Use 2-4 letters followed by 3-8 digits, "
            f"for example {student_id_example}."
        )

    # 3. Name: letters (any language), spaces, apostrophes, hyphens and periods.
    if "full_name" not in result.errors:
        letters = sum(1 for ch in full_name if ch.isalpha())
        bad = [ch for ch in full_name if not (ch.isalpha() or ch in NAME_ALLOWED_PUNCTUATION)]
        if bad:
            result.errors["full_name"] = (
                "Full name may contain only letters, spaces, apostrophes ('), hyphens (-) "
                "and periods (.)."
            )
        elif letters < 2:
            result.errors["full_name"] = "Full name must contain at least 2 letters."

    # 4. Email format
    if "email" not in result.errors:
        local_part = email.split("@", 1)[0] if "@" in email else ""
        if not EMAIL_RE.fullmatch(email) or len(local_part) > 64:
            result.errors["email"] = (
                "Email address is not valid. Use the format name@example.com."
            )

    # 5. Department must be one of the configured options (case-insensitive).
    if "department" not in result.errors and departments:
        lookup = {d.casefold(): d for d in departments}
        canonical = lookup.get(department.casefold())
        if canonical is None:
            result.errors["department"] = "Please choose a department from the list."
        else:
            department = canonical

    result.cleaned = {
        "student_id": student_id,
        "full_name": full_name,
        "name_key": make_name_key(full_name),
        "email": email,
        "department": department,
    }
    return result
