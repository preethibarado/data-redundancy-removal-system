"""
services.py - The "submit a record" workflow (business logic).

    user input
       -> validate + normalise      (validators.py)
       -> duplicate detection       (duplicate_detector.py)
       -> INSERT inside a transaction
       -> database UNIQUE constraints are the final safety net
       -> outcome returned to the route, which renders the result page

Why both an application check AND database constraints?
The pre-insert query gives friendly explanations, but between that query and
the INSERT another request could save the same student (a race condition).
The UNIQUE constraints make the database reject the second insert; we catch
the IntegrityError, roll back and report it as a duplicate - never as success.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from duplicate_detector import (
    ACCEPTED_CLASSIFICATIONS,
    Classification,
    DetectionResult,
    DuplicateDetector,
    DuplicateRules,
    MatchInfo,
)
from models import Student, SubmissionLog, db
from validators import validate_student

logger = logging.getLogger("redundancy")


@dataclass
class SubmissionOutcome:
    classification: Classification
    message: str
    reasons: list[str] = field(default_factory=list)
    matches: list[MatchInfo] = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    cleaned: dict = field(default_factory=dict)
    student: dict | None = None

    @property
    def accepted(self) -> bool:
        return self.classification in ACCEPTED_CLASSIFICATIONS and self.student is not None


def _record_attempt(classification: Classification, reason_code: str) -> None:
    """Store an anonymous statistics row. Failure here must never break the
    main request, so errors are logged and swallowed."""
    try:
        db.session.add(SubmissionLog(outcome=classification.value, reason_code=reason_code[:60]))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.warning("Could not write submission statistics row")


def _from_detection(detection: DetectionResult, cleaned: dict, message: str) -> SubmissionOutcome:
    return SubmissionOutcome(
        classification=detection.classification,
        message=message,
        reasons=detection.reasons,
        matches=detection.matches,
        cleaned=cleaned,
    )


def submit_student(raw: dict) -> SubmissionOutcome:
    config = current_app.config

    # 1) Validate ----------------------------------------------------------
    validation = validate_student(
        raw,
        student_id_pattern=config["STUDENT_ID_PATTERN"],
        departments=config["DEPARTMENTS"],
        student_id_example=config["STUDENT_ID_EXAMPLE"],
    )
    if not validation.is_valid:
        logger.info("Submission rejected: invalid fields=%s", sorted(validation.errors))
        _record_attempt(Classification.INVALID, "invalid:" + ",".join(sorted(validation.errors)))
        return SubmissionOutcome(
            classification=Classification.INVALID,
            message="The record was rejected because some fields are invalid.",
            reasons=list(validation.errors.values()),
            errors=validation.errors,
            cleaned=validation.cleaned,
        )
    cleaned = validation.cleaned

    # 2) Detect duplicates -------------------------------------------------
    detector = DuplicateDetector(db.session, DuplicateRules.from_config(config))
    try:
        detection = detector.check(cleaned)
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Database error during duplicate check")
        _record_attempt(Classification.ERROR, "db_error_check")
        return SubmissionOutcome(
            Classification.ERROR,
            "The record was NOT saved because the database could not be reached. "
            "Please try again in a moment.",
            cleaned=cleaned,
        )

    if not detection.accepted:
        logger.info("Submission rejected: %s", detection.reason_code)
        _record_attempt(detection.classification, detection.reason_code)
        return _from_detection(
            detection, cleaned, "The record was rejected and nothing was added to the database."
        )

    # 3) Insert inside a transaction ----------------------------------------
    student = Student(
        student_id=cleaned["student_id"],
        full_name=cleaned["full_name"],
        name_key=cleaned["name_key"],
        email=cleaned["email"],
        department=cleaned["department"],
    )
    try:
        db.session.add(student)
        db.session.commit()
    except IntegrityError:
        # A concurrent request saved the same identifiers first.
        db.session.rollback()
        logger.info("Insert blocked by UNIQUE constraint (concurrent duplicate)")
        classification = Classification.EXACT_DUPLICATE
        reasons = [
            "The database UNIQUE constraint blocked this insert: a record with the same "
            "student ID or email was saved at the same moment by another submission."
        ]
        matches: list[MatchInfo] = []
        try:
            # Re-check so the user sees WHICH stored record caused the rejection.
            retry = detector.check(cleaned)
            if not retry.accepted:
                classification = retry.classification
                reasons += retry.reasons
                matches = retry.matches
        except SQLAlchemyError:
            db.session.rollback()
        _record_attempt(classification, "integrity_constraint")
        return SubmissionOutcome(
            classification,
            "The record was rejected and nothing was added to the database.",
            reasons=reasons,
            matches=matches,
            cleaned=cleaned,
        )
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Database error while inserting a record")
        _record_attempt(Classification.ERROR, "db_error_insert")
        return SubmissionOutcome(
            Classification.ERROR,
            "The record was NOT saved because of a database error. Please try again.",
            cleaned=cleaned,
        )

    logger.info("Record stored: classification=%s", detection.classification.value)
    stored = student.to_dict()
    _record_attempt(detection.classification, detection.reason_code)
    message = (
        "The record is unique and verified - it was saved to the database."
        if detection.classification is Classification.UNIQUE
        else "The record was saved, but it looks similar to an existing student. "
             "Please review the warning below."
    )
    outcome = _from_detection(detection, cleaned, message)
    outcome.student = stored
    return outcome
