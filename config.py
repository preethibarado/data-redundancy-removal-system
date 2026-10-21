"""
config.py - Application configuration.

All settings live here so that the same code can run in three environments:

* development - your laptop, using a local SQLite file (instance/dev.db)
* testing     - automated tests, using a separate throw-away SQLite database
* production  - the cloud, using PostgreSQL supplied through DATABASE_URL

Select the environment with the APP_ENV environment variable
(development | testing | production). Secrets are NEVER hard-coded here:
they are read from environment variables (or a local, git-ignored .env file).
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load variables from a local .env file if one exists (ignored by git).
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(url: str | None) -> str | None:
    """Some hosts still hand out 'postgres://' URLs, which SQLAlchemy 2.x
    no longer accepts. Rewrite them to 'postgresql://'."""
    if url and url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


DEFAULT_DEPARTMENTS = [
    "Computer Science",
    "Information Technology",
    "Electronics and Communication",
    "Electrical Engineering",
    "Mechanical Engineering",
    "Civil Engineering",
    "Business Administration",
    "Mathematics",
    "Physics",
    "Other",
]


class Config:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    RECORDS_PER_PAGE = int(os.environ.get("RECORDS_PER_PAGE", "10"))
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    # ------------------------------------------------------------------
    # Validation rules
    # ------------------------------------------------------------------
    # Student ID: 2-4 capital letters followed by 3-8 digits, e.g. CS2024001.
    # Input is upper-cased before this check, so "cs2024001" is accepted too.
    STUDENT_ID_PATTERN = os.environ.get("STUDENT_ID_PATTERN", r"^[A-Z]{2,4}[0-9]{3,8}$")
    STUDENT_ID_EXAMPLE = os.environ.get("STUDENT_ID_EXAMPLE", "CS2024001")
    DEPARTMENTS = DEFAULT_DEPARTMENTS

    # ------------------------------------------------------------------
    # Duplicate-detection rules (see README "Duplicate-detection rules")
    # ------------------------------------------------------------------
    # Rule 1 + 2 (student_id and email must be unique) are ALWAYS enforced,
    # because they are also enforced by database UNIQUE constraints.
    #
    # Rule 3: name similarity is only a WARNING signal, never a rejection.
    ENABLE_POSSIBLE_DUPLICATE_CHECK = _env_bool("ENABLE_POSSIBLE_DUPLICATE_CHECK", True)
    # 0.0 - 1.0. Higher = stricter (fewer warnings). 0.85 catches typos such as
    # "Ananya Sharma" vs "Ananya Sharmaa" but not "Ananya Sharma" vs "Ananya Verma".
    NAME_SIMILARITY_THRESHOLD = float(os.environ.get("NAME_SIMILARITY_THRESHOLD", "0.85"))
    # Upper bound on how many stored rows are compared per submission, so a
    # large table is never loaded completely into memory.
    MAX_SIMILARITY_CANDIDATES = int(os.environ.get("MAX_SIMILARITY_CANDIDATES", "500"))
    MAX_POSSIBLE_MATCHES_SHOWN = 5


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.environ.get("DATABASE_URL")) or (
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "dev.db")
    )


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False  # individual tests re-enable it when needed
    SECRET_KEY = "test-secret-key"
    # Tests override this with a temporary file per test (see tests/conftest.py).
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # cookies only travel over HTTPS
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.environ.get("DATABASE_URL"))
    # pool_pre_ping transparently replaces connections the cloud DB has closed.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    if os.environ.get("DB_SSLMODE"):
        # e.g. DB_SSLMODE=require when connecting over the public internet.
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"sslmode": os.environ["DB_SSLMODE"]}


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
