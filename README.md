# Data Redundancy Removal System

**CodeAlpha Cloud Computing Internship – Task 1**

A Flask web application that validates student records, compares each new submission with the data already in the database, classifies it (unique / possible duplicate / exact duplicate / conflict / invalid), and **stores only unique, verified records**. Duplicate prevention is guaranteed by **database UNIQUE constraints** as well as application logic, so it holds even when two users submit the same record at the same moment.

> **Status (honest):** The source code, migrations and 37 automated tests have been run and verified locally (SQLite **and** PostgreSQL). Cloud deployment instructions for **Render** are included in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). This project has **not** been deployed by the author of this README yet. You must do that with your own account and then report your own live URL.

---

## Table of contents
1. [Problem statement](#1-problem-statement)
2. [Objectives & requirement mapping](#2-objectives--official-requirement-mapping)
3. [Features](#3-features)
4. [Architecture](#4-architecture)
5. [Duplicate-detection rules](#5-duplicate-detection-rules)
6. [Database schema](#6-database-schema)
7. [Technologies](#7-technologies)
8. [Project structure](#8-project-structure)
9. [Run it locally (step by step)](#9-run-it-locally-step-by-step)
10. [Testing](#10-testing)
11. [Deployment](#11-deployment)
12. [Publishing to GitHub](#12-publishing-to-github)
13. [Security](#13-security)
14. [Limitations & future enhancements](#14-limitations--future-enhancements)
15. [Further documentation](#15-further-documentation)

---

## 1. Problem statement
When data is entered by many people, the same entity (e.g. a student) is often stored more than once, sometimes with small differences in spacing or letter case. Redundant rows waste storage, make reports wrong (one student counted twice) and cause conflicting information. On the other hand, a naive filter that rejects anything "similar" will wrongly block legitimate records, such as two different students who share a name (a **false positive**).

## 2. Objectives & official requirement mapping

| # | Official CodeAlpha requirement | How this project satisfies it |
|---|---|---|
| 1 | Identify and classify redundant data **and false positives** | `duplicate_detector.py` classifies every submission as `UNIQUE`, `POSSIBLE_DUPLICATE`, `EXACT_DUPLICATE`, `CONFLICT` or `INVALID`, with a reason. Name similarity only produces a warning, so false positives are never rejected. |
| 2 | Validate new data against existing data | `services.submit_student()` validates the input (`validators.py`), then queries existing rows by student ID, email and similar names before inserting. |
| 3 | Prevent duplicates from being added to the cloud database | Rejected classifications are never inserted, and PostgreSQL `UNIQUE` constraints on `student_id` and `email` block any duplicate that slips past the check (race conditions). |
| 4 | Append only unique and verified entries | Insertion happens only after validation succeeds **and** the classification is `UNIQUE` or `POSSIBLE_DUPLICATE`, inside a transaction. |
| 5 | Improve accuracy and efficiency | Normalisation (trim, lower-case email, upper-case ID) catches "hidden" duplicates. Indexes speed up lookups, similarity checks compare only a bounded set of candidates, and pagination avoids loading the whole table. |

## 3. Features
- Dashboard showing stored-record count and **real** validation statistics (nothing is faked; it starts at zero).
- Add Student form with server-side validation and friendly per-field error messages.
- A Duplicate Detection Result page explaining **why** each record was accepted or rejected and which stored record it matched.
- A Student Records table with search (ID, name, email) and pagination.
- Configurable rules (similarity threshold, on/off switch, ID pattern) through environment variables.
- `/health` endpoint for cloud health checks.
- CSRF protection, auto-escaping, a parameterised ORM, and no stack traces shown to users.

## 4. Architecture

```mermaid
flowchart LR
    U[User's browser<br/>HTML + Bootstrap + app.js] -- HTTPS form POST / GET --> F

    subgraph Cloud host [Cloud host – e.g. Render Web Service]
      F[Flask routes<br/>app.py] --> S[Submission service<br/>services.py]
      S --> V[Validation & normalisation<br/>validators.py]
      S --> D[Duplicate detector<br/>duplicate_detector.py]
      S --> M[ORM models<br/>models.py / SQLAlchemy]
      C[(Environment variables<br/>SECRET_KEY, DATABASE_URL)] -.-> F
    end

    M -- SQL over TLS / private network --> P[(Managed PostgreSQL<br/>UNIQUE student_id, UNIQUE email)]
```

**Data flow for one submission**
1. The browser POSTs the form, including its CSRF token.
2. `app.py` passes the fields to `services.submit_student()`.
3. **Validate**: required fields, ID format, email format, length limits, department list. Values are normalised. If anything fails, the result is `INVALID`, nothing is stored, and the errors are shown on the form.
4. **Detect**: the detector looks up existing rows with the same student ID or email, and with similar names.
5. `EXACT_DUPLICATE` or `CONFLICT` means the record is rejected, nothing is stored, and the reasons are shown.
6. `UNIQUE` or `POSSIBLE_DUPLICATE` means an `INSERT` runs inside a transaction.
7. If the database raises `IntegrityError` (another request inserted the same ID/email a moment earlier), the transaction is rolled back and the result is reported as a duplicate. **Never as success.**
8. Any other database error is rolled back and reported as "NOT saved".
9. An anonymous statistics row (outcome only, no personal data) is written to `submission_logs`.

## 5. Duplicate-detection rules

| Rule | Condition | Result | Why this rule is appropriate |
|---|---|---|---|
| R0 Validation | Missing or malformed field | **INVALID**, rejected | Bad data must never reach the database. |
| R1 Unique student ID | Normalised `student_id` already stored | Duplicate or conflict, rejected | A student ID is issued by the institution and identifies exactly one student. |
| R2 Unique email | Normalised (lower-case) `email` already stored | Duplicate or conflict, rejected | Email addresses are personal and case-insensitive in practice. |
| R3 Exact duplicate | Same ID **and** email, **and** same name and department | **EXACT_DUPLICATE**, rejected | It is a redundant copy of an existing row. |
| R4 Conflict | ID or email matches, but other details differ | **CONFLICT**, rejected | One identifier cannot describe two different sets of facts. Saving would corrupt the data. |
| R5 Similar name | New ID and email, but name similarity ≥ `NAME_SIMILARITY_THRESHOLD` (default 0.85) | **POSSIBLE_DUPLICATE**, **accepted** with a warning | Different people can share a name, so a name alone must never block a record. |
| R6 Unique | None of the above | **UNIQUE**, accepted | Valid and new. |

**Key terms**
- **Exact duplicate**: the same real-world record submitted again. It is rejected.
- **Possible duplicate**: looks similar (usually by name) but has different reliable identifiers. It is stored, and the user is warned.
- **Invalid record**: fails format or required-field validation. It is rejected before any comparison.
- **False positive**: a legitimate new record that a naive system *wrongly* flags as a duplicate (e.g. two students both called "Rahul Kumar"). This system avoids false positives by rejecting **only** on reliable identifiers and treating name similarity as a review signal.

**Similarity algorithm:** Python's `difflib.SequenceMatcher` ratio on case-folded names. It also compares the words sorted alphabetically, so "Kumar Ravi" matches "Ravi Kumar". Only rows sharing at least one name word are compared (at most `MAX_SIMILARITY_CANDIDATES`, default 500).

## 6. Database schema

```mermaid
erDiagram
    students {
        int id PK
        varchar(20) student_id "UNIQUE, normalised upper-case"
        varchar(100) full_name "as typed (spaces collapsed)"
        varchar(100) name_key "case-folded, indexed, for search/similarity"
        varchar(254) email "UNIQUE, lower-case"
        varchar(100) department
        timestamptz created_at "indexed"
    }
    submission_logs {
        int id PK
        varchar(30) outcome "indexed"
        varchar(60) reason_code "no personal data"
        timestamptz created_at
    }
```

## 7. Technologies
Python 3.12 (3.10+ works) · Flask 3 · Flask-SQLAlchemy / SQLAlchemy 2.1 · Flask-Migrate (Alembic) · Flask-WTF (CSRF) · Bootstrap 5 · SQLite (local) · PostgreSQL (cloud, `psycopg` 3 driver) · Gunicorn · pytest · Git/GitHub · Render (hosting).

## 8. Project structure

```
CodeAlpha_DataRedundancyRemoval/
├── app.py                  # Flask app factory, routes, error handlers, CLI
├── config.py               # Dev / test / production settings + duplicate rules
├── models.py               # SQLAlchemy tables with UNIQUE constraints & indexes
├── validators.py           # Server-side validation and gentle normalisation
├── duplicate_detector.py   # Classification logic (exact / conflict / possible / unique)
├── services.py             # Validate → detect → transactional insert workflow
├── requirements.txt        # Pinned dependencies
├── render.yaml             # Optional Render Blueprint (web service + Postgres)
├── pytest.ini              # Test configuration
├── .env.example            # Template for environment variables (no real secrets)
├── .gitignore              # Keeps .env, venv, *.db out of Git
├── templates/              # Jinja2 HTML pages (auto-escaped)
│   ├── base.html  index.html  add_student.html
│   ├── records.html  duplicate_results.html  error.html
├── static/css/style.css    # Custom styles
├── static/js/app.js        # Small UX helpers (server still validates everything)
├── migrations/             # Alembic migration scripts (database version control)
├── tests/                  # 37 automated tests
│   ├── conftest.py  test_validation.py  test_duplicates.py  test_routes.py
└── docs/                   # Project report, deployment guide, demo script, checklist
```

## 9. Run it locally (step by step)

### 9.1 Install prerequisites
1. **Python 3.10 or newer**: download it from <https://www.python.org/downloads/>. On Windows, tick **"Add python.exe to PATH"** in the installer.
2. **Git**: <https://git-scm.com/downloads>.
3. Check both are installed by opening a new terminal (Windows: *PowerShell*):
   ```powershell
   python --version
   git --version
   ```

### 9.2 Create a virtual environment and install dependencies

**Windows PowerShell**
```powershell
cd CodeAlpha_DataRedundancyRemoval
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```
> If PowerShell says *"running scripts is disabled"*, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again.

**macOS / Linux**
```bash
cd CodeAlpha_DataRedundancyRemoval
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and set `SECRET_KEY` to a random value. You can generate one with:
`python -c "import secrets; print(secrets.token_hex(32))"`. Leave `DATABASE_URL` empty to use a local SQLite file.

### 9.3 Create the database tables
```powershell
flask --app app db upgrade
```
This applies the scripts in `migrations/` and creates `instance/dev.db`. (`flask --app app init-db` is a quick alternative that creates the tables without migrations.)

### 9.4 Start the app
```powershell
flask --app app run --debug
```
Then open <http://127.0.0.1:5000>.

### 9.5 Common local errors

| Error | Cause and fix |
|---|---|
| `'flask' is not recognized` | The virtual environment is not active. Run `.\venv\Scripts\Activate.ps1` again. |
| `ModuleNotFoundError: No module named 'flask'` | Run `pip install -r requirements.txt` inside the active venv. |
| `no such table: students` | You skipped step 9.3. Run `flask --app app db upgrade`. |
| `ModuleNotFoundError: psycopg` | `DATABASE_URL` points to PostgreSQL but dependencies are missing. Reinstall the requirements. |
| `Address already in use` | Another app is using port 5000. Run `flask --app app run --port 5001`. |
| Form says "Form expired" | The CSRF token expired. Reload the page and submit again. |
| App connects to the wrong database | The `flask` command also loads a `.env` from **parent** folders. Keep the project in its own folder, check `DATABASE_URL` in your `.env`, or run with `$env:FLASK_SKIP_DOTENV="1"`. |

## 10. Testing
Tests use a **separate temporary database** for every test, so your dev data is never touched.

```powershell
python -m pytest -v
```

**Verified result** (run during development on Python 3.11, both databases):
```
37 passed            # SQLite (default)
37 passed            # PostgreSQL, using TEST_DATABASE_URL
```

To run the same tests on PostgreSQL, point `TEST_DATABASE_URL` at an **empty, separate** database. Its tables are dropped after each test.
```powershell
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/redundancy_test"
python -m pytest -q
```

| Required scenario | Test(s) |
|---|---|
| 1 Valid record inserted | `test_valid_new_record_is_inserted`, `test_valid_submission_shows_accepted` |
| 2 Duplicate student ID rejected | `test_exact_duplicate_student_id_is_rejected`, `test_duplicate_submission_shows_rejection_with_reason` |
| 3 Duplicate email rejected | `test_duplicate_email_is_rejected` |
| 4 Same name, different students | `test_two_students_with_same_name_are_both_stored` |
| 5 Possible duplicate warning | `test_possible_duplicate_produces_warning` |
| 6 Invalid email rejected | `test_invalid_email_is_rejected` |
| 7 Missing fields rejected | `test_missing_required_fields_are_rejected` |
| 8 Normalisation | `test_whitespace_and_email_case_normalisation`, `test_name_case_is_preserved` |
| 9 Conflicting records | `test_same_student_id_with_different_email_is_conflict`, `test_same_identifiers_different_department_is_conflict` |
| 10 Concurrent duplicates | `test_concurrent_submissions_store_only_one_record`, `test_unique_constraint_blocks_duplicate_when_precheck_is_bypassed` |
| 11 DB errors are not shown as success | `test_database_error_does_not_report_success`, `test_database_error_page_is_not_success` |
| 12 Records page shows only stored records | `test_records_page_shows_only_stored_records` |

## 11. Deployment
A complete, beginner-friendly guide for **Render (Web Service + Render Postgres)** is in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
Production start command: `flask --app app db upgrade && gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`.

> Render's free Postgres **expires 30 days after creation**, and free web services sleep after 15 minutes idle (about 1 minute to wake up). This is fine for an internship demo. Record your demo video within the 30 days.

## 12. Publishing to GitHub
1. On <https://github.com/new>, create an **empty** public repository named `CodeAlpha_DataRedundancyRemoval`. Do not add a README, .gitignore or licence.
2. In the project folder:
```powershell
git init
git add .
git status            # check that .env, venv/ and instance/ are NOT listed
git commit -m "Data Redundancy Removal System - CodeAlpha Task 1"
git branch -M main
git remote add origin https://github.com/<your-username>/CodeAlpha_DataRedundancyRemoval.git
git push -u origin main
```
GitHub asks you to sign in. When prompted for a password, use a *Personal Access Token* (or sign in through the browser window).

**Screenshots:** take them from your running app (Dashboard, Add Student, a rejected duplicate, Records). Save them in `docs/screenshots/` and link them here, for example `![Dashboard](docs/screenshots/dashboard.png)`. No screenshots are included yet because they must come from your own run.

## 13. Security
- **SQL injection**: all queries go through the SQLAlchemy ORM, which uses parameters.
- **XSS**: Jinja2 auto-escapes all output (covered by `test_user_content_is_escaped`).
- **CSRF**: Flask-WTF `CSRFProtect` on every POST (covered by `test_csrf_token_required_when_enabled`).
- **Secrets**: read from environment variables. `.env` is git-ignored. Production refuses to start without a `SECRET_KEY` and `DATABASE_URL`.
- **Error handling**: users see friendly messages. Stack traces and SQL go only to server logs (covered by `test_database_error_page_is_not_success`).
- **Data minimisation**: only four fields are collected, with no passwords. Rejected submissions are **not** stored; only an anonymous outcome code is logged.
- **Production cookies**: `Secure`, `HttpOnly`, `SameSite=Lax`. Render provides HTTPS automatically.

## 14. Limitations & future enhancements
**Limitations**
- Name similarity is character-based. It does not understand nicknames ("Bob"/"Robert"), transliterations or phonetics, and the 0.85 threshold is a heuristic.
- The candidate search uses `LIKE '%word%'`, which cannot use a normal B-tree index. For very large tables use PostgreSQL `pg_trgm`.
- There is no login. Anyone who can open the URL can add records, which is acceptable for a demo but not for real student data.
- There is no edit/delete UI. A conflicting record must be corrected by an administrator.
- It has been tested with a single small instance. It is **not** load-tested and **not** highly available.
- Render's free Postgres expires after 30 days and has no backups.

**Future enhancements:** authentication and roles · an admin review queue for possible duplicates · edit/merge records · CSV bulk import with a per-row report · `pg_trgm` / phonetic matching · REST API · audit log · scheduled backups.

## 15. Further documentation
- [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md): full project report (abstract → conclusion)
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): cloud deployment guide (Render)
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md): 3–5 minute video script
- [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md): final submission checklist
