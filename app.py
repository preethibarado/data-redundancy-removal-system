"""
app.py - Flask application factory, routes and CLI commands.

Run locally:      flask --app app run --debug
Run in the cloud: gunicorn "app:create_app()"
"""
from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, render_template, request
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError, CSRFProtect
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from config import CONFIG_BY_NAME
from duplicate_detector import Classification
from models import Student, SubmissionLog, db
from services import submit_student

migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    config_name = config_name or os.environ.get("APP_ENV", "development")
    if config_name not in CONFIG_BY_NAME:
        raise RuntimeError(f"Unknown APP_ENV '{config_name}'. Use development, testing or production.")

    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name])
    if overrides:
        app.config.update(overrides)

    if config_name == "production":
        if not app.config.get("SQLALCHEMY_DATABASE_URI"):
            raise RuntimeError("DATABASE_URL must be set in production.")
        if app.config["SECRET_KEY"] == "dev-only-insecure-key-change-me":
            raise RuntimeError("SECRET_KEY must be set to a long random value in production.")

    os.makedirs(app.instance_path, exist_ok=True)  # holds the local SQLite file
    logging.basicConfig(
        level=app.config.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    register_routes(app)
    register_error_handlers(app)
    register_cli(app)
    return app


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def register_routes(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        return {"Classification": Classification}

    @app.get("/")
    def index():
        total = db.session.scalar(select(func.count(Student.id))) or 0
        outcome_rows = db.session.execute(
            select(SubmissionLog.outcome, func.count(SubmissionLog.id)).group_by(SubmissionLog.outcome)
        ).all()
        stats = {c.value: 0 for c in Classification}
        for outcome, count in outcome_rows:
            stats[outcome] = count
        attempts = sum(stats.values())
        accepted = stats["unique"] + stats["possible_duplicate"]
        prevented = stats["exact_duplicate"] + stats["conflict"]
        departments = db.session.execute(
            select(Student.department, func.count(Student.id))
            .group_by(Student.department)
            .order_by(func.count(Student.id).desc())
        ).all()
        recent = db.session.execute(
            select(Student).order_by(Student.created_at.desc(), Student.id.desc()).limit(5)
        ).scalars().all()
        return render_template(
            "index.html",
            total=total,
            stats=stats,
            attempts=attempts,
            accepted=accepted,
            prevented=prevented,
            departments=departments,
            recent=recent,
        )

    @app.route("/students/add", methods=["GET", "POST"])
    def add_student():
        if request.method == "GET":
            return render_template("add_student.html", values={}, errors={})

        form = {k: request.form.get(k, "") for k in ("student_id", "full_name", "email", "department")}
        outcome = submit_student(form)

        if outcome.classification is Classification.INVALID:
            return render_template(
                "add_student.html", values=form, errors=outcome.errors, outcome=outcome
            ), 400

        status = 201 if outcome.accepted else (503 if outcome.classification is Classification.ERROR else 409)
        return render_template("duplicate_results.html", outcome=outcome, submitted=form), status

    @app.get("/records")
    def records():
        q = request.args.get("q", "").strip()[:100]
        page = request.args.get("page", 1, type=int) or 1
        stmt = select(Student)
        if q:
            pattern = f"%{q.replace('%', '').replace('_', '')}%"
            stmt = stmt.where(
                or_(
                    Student.student_id.ilike(pattern),
                    Student.name_key.ilike(pattern.casefold()),
                    Student.email.ilike(pattern),
                )
            )
        stmt = stmt.order_by(Student.created_at.desc(), Student.id.desc())
        pagination = db.paginate(
            stmt, page=max(page, 1), per_page=app.config["RECORDS_PER_PAGE"], error_out=False
        )
        total = db.session.scalar(select(func.count(Student.id))) or 0
        return render_template("records.html", pagination=pagination, q=q, total=total)

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok", database="ok")
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Health check failed")
            return jsonify(status="error", database="unreachable"), 503


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def csrf_error(err):
        return render_template(
            "error.html", code=400, title="Form expired",
            message="Your form session expired or was invalid. Please reload the page and try again.",
        ), 400

    @app.errorhandler(404)
    def not_found(err):
        return render_template(
            "error.html", code=404, title="Page not found",
            message="The page you requested does not exist.",
        ), 404

    @app.errorhandler(500)
    def server_error(err):
        db.session.rollback()
        return render_template(
            "error.html", code=500, title="Something went wrong",
            message="An unexpected error occurred. No details are shown for security reasons.",
        ), 500


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Quick start: create tables directly (use 'flask db upgrade' for migrations)."""
        db.create_all()
        print("Database tables created.")


if __name__ == "__main__":  # pragma: no cover
    create_app().run()
