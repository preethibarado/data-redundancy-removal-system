"""
duplicate_detector.py - Classifies a VALIDATED record against stored data.

Classifications
---------------
UNIQUE              No stored record shares the student ID or email, and no
                    similar name was found.                     -> ACCEPTED
POSSIBLE_DUPLICATE  Identifiers are new, but the name is identical or very
                    similar to a stored student. Different people can share a
                    name, so this is only a WARNING.            -> ACCEPTED
EXACT_DUPLICATE     A stored record has the same student ID AND email and the
                    same name/department - it is a redundant copy. -> REJECTED
CONFLICT            An identifier (student ID or email) already exists but is
                    attached to different information (e.g. same ID with a
                    different email). Saving it would corrupt data. -> REJECTED
INVALID             Failed validation (decided in validators.py). -> REJECTED
ERROR               A database problem prevented saving.     -> NOT SAVED

False positives
---------------
A false positive is a legitimate new record wrongly treated as a duplicate.
To avoid them we only REJECT based on reliable identifiers (student ID and
normalised email). Name similarity can be wrong (two real "Rahul Kumar"s), so
it never blocks a record - it only shows a review warning with the reason.

The detector is written against a small interface (a SQLAlchemy session and a
model with student_id / email / name_key columns) so the same idea can be
reused for other record types later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum

from sqlalchemy import or_, select

from models import Student
from validators import make_name_key


class Classification(str, Enum):
    UNIQUE = "unique"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    EXACT_DUPLICATE = "exact_duplicate"
    CONFLICT = "conflict"
    INVALID = "invalid"
    ERROR = "error"

    @property
    def label(self) -> str:
        return {
            "unique": "Unique record",
            "possible_duplicate": "Possible duplicate (accepted with warning)",
            "exact_duplicate": "Exact duplicate",
            "conflict": "Conflicting record",
            "invalid": "Invalid record",
            "error": "Not saved (database error)",
        }[self.value]


ACCEPTED_CLASSIFICATIONS = {Classification.UNIQUE, Classification.POSSIBLE_DUPLICATE}


@dataclass
class DuplicateRules:
    """Configurable knobs (populated from config.py)."""

    enable_possible_duplicate_check: bool = True
    name_similarity_threshold: float = 0.85
    max_candidates: int = 500
    max_matches_shown: int = 5

    @classmethod
    def from_config(cls, config) -> "DuplicateRules":
        return cls(
            enable_possible_duplicate_check=config.get("ENABLE_POSSIBLE_DUPLICATE_CHECK", True),
            name_similarity_threshold=config.get("NAME_SIMILARITY_THRESHOLD", 0.85),
            max_candidates=config.get("MAX_SIMILARITY_CANDIDATES", 500),
            max_matches_shown=config.get("MAX_POSSIBLE_MATCHES_SHOWN", 5),
        )


@dataclass
class MatchInfo:
    """A stored record related to the submission, plus why it matched."""

    record: dict
    matched_on: str  # "student_id" | "email" | "student_id+email" | "name"
    reason: str
    score: float | None = None


@dataclass
class DetectionResult:
    classification: Classification
    reasons: list[str] = field(default_factory=list)
    matches: list[MatchInfo] = field(default_factory=list)
    reason_code: str = ""

    @property
    def accepted(self) -> bool:
        return self.classification in ACCEPTED_CLASSIFICATIONS


def name_similarity(a: str, b: str) -> float:
    """Similarity between two names, 0.0 (different) to 1.0 (identical).

    Uses difflib's SequenceMatcher ratio on case-folded names, and also on the
    words sorted alphabetically so "Kumar Ravi" ~ "Ravi Kumar".
    Limitations: purely character based - it knows nothing about nicknames
    ("Bob" vs "Robert"), transliteration ("Mohammad" vs "Muhammed" scores
    fairly high but not 1.0) or cultural name order beyond simple swaps.
    """
    key_a, key_b = make_name_key(a), make_name_key(b)
    if not key_a or not key_b:
        return 0.0
    direct = SequenceMatcher(None, key_a, key_b).ratio()
    sorted_a = " ".join(sorted(key_a.split()))
    sorted_b = " ".join(sorted(key_b.split()))
    swapped = SequenceMatcher(None, sorted_a, sorted_b).ratio()
    return round(max(direct, swapped), 3)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class DuplicateDetector:
    def __init__(self, session, rules: DuplicateRules | None = None, model=Student):
        self.session = session
        self.rules = rules or DuplicateRules()
        self.model = model

    # -- public API ---------------------------------------------------------
    def check(self, cleaned: dict) -> DetectionResult:
        """Classify an already-validated, normalised record."""
        model = self.model
        by_id = self.session.execute(
            select(model).where(model.student_id == cleaned["student_id"])
        ).scalar_one_or_none()
        by_email = self.session.execute(
            select(model).where(model.email == cleaned["email"])
        ).scalar_one_or_none()

        if by_id is not None or by_email is not None:
            return self._classify_identifier_match(cleaned, by_id, by_email)

        if self.rules.enable_possible_duplicate_check:
            matches = self._find_similar_names(cleaned)
            if matches:
                reasons = [m.reason for m in matches]
                reasons.append(
                    "The student ID and email are new, so this record was ACCEPTED. "
                    "Different students can share a name - please just double-check it "
                    "is not the same person."
                )
                return DetectionResult(
                    Classification.POSSIBLE_DUPLICATE, reasons, matches, "similar_name"
                )

        return DetectionResult(
            Classification.UNIQUE,
            ["No stored record uses this student ID or email address, and no similar "
             "name was found. The record is unique and verified."],
            [],
            "unique",
        )

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _differences(existing, cleaned: dict) -> list[str]:
        diffs = []
        if existing.email != cleaned["email"]:
            diffs.append("email address")
        if existing.name_key != cleaned["name_key"]:
            diffs.append("full name")
        if existing.department != cleaned["department"]:
            diffs.append("department")
        return diffs

    def _classify_identifier_match(self, cleaned, by_id, by_email) -> DetectionResult:
        # Same stored row matched on BOTH identifiers.
        if by_id is not None and by_email is not None and by_id.id == by_email.id:
            existing = by_id
            diffs = self._differences(existing, cleaned)
            match_on = "student_id+email"
            if not diffs:
                return DetectionResult(
                    Classification.EXACT_DUPLICATE,
                    [f"Student ID {existing.student_id} with email {existing.email} is "
                     "already stored with identical details. Saving it again would only "
                     "create a redundant copy, so it was rejected."],
                    [MatchInfo(existing.to_dict(), match_on, "Same student ID, email, name "
                               "and department")],
                    "exact_duplicate",
                )
            return DetectionResult(
                Classification.CONFLICT,
                [f"Student ID {existing.student_id} and this email are already registered, "
                 f"but the stored {', '.join(diffs)} is different. The same identifiers "
                 "cannot describe two different sets of details, so it was rejected. "
                 "If the stored data is wrong, correct the existing record instead."],
                [MatchInfo(existing.to_dict(), match_on,
                           "Same identifiers, different " + ", ".join(diffs))],
                "conflict_identifiers",
            )

        reasons: list[str] = []
        matches: list[MatchInfo] = []
        if by_id is not None:
            diffs = self._differences(by_id, cleaned)
            reasons.append(
                f"Student ID {by_id.student_id} already belongs to a stored record "
                f"whose {', '.join(diffs)} is different. A student ID must identify "
                "exactly one student."
            )
            matches.append(MatchInfo(by_id.to_dict(), "student_id",
                                     "Same student ID, different " + ", ".join(diffs)))
        if by_email is not None:
            reasons.append(
                f"Email {by_email.email} is already registered to student ID "
                f"{by_email.student_id}. An email address can belong to only one student."
            )
            matches.append(MatchInfo(by_email.to_dict(), "email",
                                     f"Same email, different student ID ({by_email.student_id})"))
        reasons.append("The record was rejected to keep the database consistent.")
        code = "conflict_student_id" if by_id is not None else "conflict_email"
        if by_id is not None and by_email is not None:
            code = "conflict_both"
        return DetectionResult(Classification.CONFLICT, reasons, matches, code)

    def _find_similar_names(self, cleaned: dict) -> list[MatchInfo]:
        """Compare the name with a LIMITED set of candidates that share at least
        one name word, instead of loading the whole table."""
        model = self.model
        tokens = [t for t in cleaned["name_key"].split() if len(t) >= 2][:5]
        if not tokens:
            return []
        conditions = [
            model.name_key.like(f"%{_escape_like(tok)}%", escape="\\") for tok in tokens
        ]
        candidates = self.session.execute(
            select(model).where(or_(*conditions)).limit(self.rules.max_candidates)
        ).scalars().all()

        matches: list[MatchInfo] = []
        for candidate in candidates:
            score = name_similarity(cleaned["full_name"], candidate.full_name)
            if score < self.rules.name_similarity_threshold:
                continue
            if score == 1.0:
                reason = (f"Same name as stored student {candidate.student_id} "
                          f"({candidate.full_name}), but with a different student ID and email.")
            else:
                reason = (f"Name is {round(score * 100)}% similar to stored student "
                          f"{candidate.student_id} ({candidate.full_name}).")
            matches.append(MatchInfo(candidate.to_dict(), "name", reason, score))
        matches.sort(key=lambda m: m.score or 0, reverse=True)
        return matches[: self.rules.max_matches_shown]
