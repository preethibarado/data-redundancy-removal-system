"""
models.py - Database tables (SQLAlchemy ORM).

The ORM builds parameterised SQL for us, which protects against SQL injection.

Integrity is enforced by the DATABASE itself, not only by Python code:
* students.student_id has a UNIQUE constraint
* students.email      has a UNIQUE constraint
So even if two requests slip past the application-level check at the same
moment, the database refuses the second insert (IntegrityError).
"""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(db.Model):
    """A verified, unique student record. Only accepted submissions land here."""

    __tablename__ = "students"
    __table_args__ = (
        db.UniqueConstraint("student_id", name="uq_students_student_id"),
        db.UniqueConstraint("email", name="uq_students_email"),
        db.Index("ix_students_name_key", "name_key"),
        db.Index("ix_students_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Normalised (trimmed + upper-cased) student identifier, e.g. CS2024001.
    student_id = db.Column(db.String(20), nullable=False)
    # Name exactly as the user typed it (only extra spaces removed).
    full_name = db.Column(db.String(100), nullable=False)
    # Case-folded copy of the name used for searching / similarity checks.
    # Keeping it separate means we never alter how the real name is displayed.
    name_key = db.Column(db.String(100), nullable=False)
    # Normalised (trimmed + lower-cased) email address.
    email = db.Column(db.String(254), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "full_name": self.full_name,
            "email": self.email,
            "department": self.department,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Student {self.student_id}>"


class SubmissionLog(db.Model):
    """One row per submission attempt, used for the dashboard statistics.

    Privacy: we store ONLY the outcome and a short reason code - no names,
    emails or IDs - so rejected personal data is never retained.
    """

    __tablename__ = "submission_logs"

    id = db.Column(db.Integer, primary_key=True)
    outcome = db.Column(db.String(30), nullable=False, index=True)
    reason_code = db.Column(db.String(60), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
