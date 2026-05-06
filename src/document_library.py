"""
document_library.py
-------------------
SQLite-backed document library for the Site Audit Agent.

Provides persistent storage and retrieval of generated site assessment report
metadata.  Every successfully generated PDF is cataloged here so that any APM
on the shared deployment can locate and re-download prior reports.

Public API
----------
init_db()
    Create data/ and reports/ directories, initialize reports.db and schema.
    Safe to call on every app startup — never drops existing data.

save_report(facility_name, client_name, apm_name, file_path) -> int
    Insert a metadata record for a newly generated report.  Returns the new
    row ID.  Raises ValueError on duplicate file_path.

search_reports(client_name, facility_name, date_from, date_to) -> list[dict]
    Return records matching the supplied filters, ordered by date_generated
    descending.  Omit all params to retrieve every record.

get_report_by_id(report_id) -> dict | None
    Return a single record dict or None if not found.

delete_report(report_id) -> bool
    Delete the DB record and the associated PDF from disk.  Returns True on
    success, False if the record was not found.

build_report_filename(facility_name, client_name) -> str
    Build a relative file path for a new report PDF following the naming
    convention: reports/{YYYY-MM-DD}_{facility_slug}_{client_slug}.pdf
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants (all relative to the project root, i.e. the working directory
# when `streamlit run app.py` is executed).
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent  # Site_Audit_Agent/
_DATA_DIR = _PROJECT_ROOT / "data"
_REPORTS_DIR = _PROJECT_ROOT / "reports"
_DB_PATH = _DATA_DIR / "reports.db"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_connection() -> sqlite3.Connection:
    """
    Open and return a new SQLite connection with WAL mode and row-factory set.

    Every public function is responsible for closing the connection it opens.
    No persistent module-level connection is kept.
    """
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain Python dict."""
    return dict(row)


# ---------------------------------------------------------------------------
# File naming helpers
# ---------------------------------------------------------------------------


def _slugify(value: str) -> str:
    """
    Convert a string to a filesystem-safe slug.

    Steps:
    1. Lowercase and strip surrounding whitespace.
    2. Remove characters that are not word chars, spaces, or hyphens.
    3. Collapse runs of whitespace, underscores, or hyphens to a single '_'.
    4. Cap the result at 40 characters.
    """
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "_", value)
    return value[:40]


def build_report_filename(facility_name: str, client_name: str) -> str:
    """
    Build a relative path for a new PDF report.

    Format: ``reports/{YYYY-MM-DD}_{facility_slug}_{client_slug}.pdf``

    If a file at the target path already exists on disk, a ``_{HHMMSS}``
    timestamp suffix is appended before the extension:
    ``reports/{YYYY-MM-DD}_{facility_slug}_{client_slug}_{HHMMSS}.pdf``

    The returned path is relative to the project root so the database record
    survives VPS migrations (no hardcoded absolute paths).

    Parameters
    ----------
    facility_name : str
        Name of the facility being assessed.
    client_name : str
        Name of the client.

    Returns
    -------
    str
        Relative path string, e.g. ``"reports/2026-05-05_white_drive_acme.pdf"``
    """
    today = date.today().isoformat()
    base_name = f"{today}_{_slugify(facility_name)}_{_slugify(client_name)}.pdf"
    rel_path = f"reports/{base_name}"

    abs_path = _PROJECT_ROOT / rel_path
    if abs_path.exists():
        # Collision: append HHMMSS suffix derived from the current local time
        suffix = datetime.now().strftime("%H%M%S")
        stem = base_name[: -len(".pdf")]
        rel_path = f"reports/{stem}_{suffix}.pdf"

    return rel_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db() -> None:
    """
    Ensure the required directories and database schema exist.

    Creates ``data/`` and ``reports/`` directories if missing, then creates
    the ``reports`` table and its three indexes if they do not already exist.

    Safe to call on every application startup — no existing data is ever
    dropped or altered.
    """
    # Create directories — exist_ok=True makes this idempotent
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    conn = _get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                facility_name   TEXT    NOT NULL,
                client_name     TEXT    NOT NULL,
                apm_name        TEXT    NOT NULL,
                date_generated  TEXT    NOT NULL,
                file_path       TEXT    NOT NULL UNIQUE
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_client_name
                ON reports (client_name COLLATE NOCASE);
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_facility_name
                ON reports (facility_name COLLATE NOCASE);
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_date_generated
                ON reports (date_generated);
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_report(
    facility_name: str,
    client_name: str,
    apm_name: str,
    file_path: str,
) -> int:
    """
    Insert a metadata record for a newly generated report.

    Parameters
    ----------
    facility_name : str
        Name of the facility assessed.
    client_name : str
        Name of the client.
    apm_name : str
        Name of the APM who generated the report.
    file_path : str
        Relative path to the PDF file (e.g. ``"reports/2026-05-05_..."``).

    Returns
    -------
    int
        The auto-incremented primary key of the newly inserted row.

    Raises
    ------
    ValueError
        If ``file_path`` already exists in the database (UNIQUE constraint).
    """
    date_generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    conn = _get_connection()
    try:
        try:
            cursor = conn.execute(
                """
                INSERT INTO reports (facility_name, client_name, apm_name,
                                     date_generated, file_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    facility_name.strip(),
                    client_name.strip(),
                    apm_name.strip(),
                    date_generated,
                    file_path,
                ),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A report with file_path '{file_path}' already exists in the library. "
                f"Original error: {exc}"
            ) from exc
    finally:
        conn.close()


def search_reports(
    client_name: str | None = None,
    facility_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """
    Return report records matching the supplied filters.

    All filters are optional; omitting all returns every record.

    Parameters
    ----------
    client_name : str | None
        Case-insensitive partial match against the ``client_name`` column
        (SQL ``LIKE '%value%'``).
    facility_name : str | None
        Case-insensitive partial match against the ``facility_name`` column.
    date_from : str | None
        Inclusive lower bound, format ``YYYY-MM-DD``.  Compared against the
        date portion of ``date_generated``.
    date_to : str | None
        Inclusive upper bound, format ``YYYY-MM-DD``.

    Returns
    -------
    list[dict]
        Matching records as plain dicts, ordered by ``date_generated``
        descending (most recent first).  Empty list on no matches or if the
        database has not been initialized (``init_db()`` is called implicitly
        in that case).
    """
    # Implicitly initialize if the database file does not yet exist
    if not _DB_PATH.exists():
        init_db()
        return []

    conditions: list[str] = []
    params: list[str] = []

    if client_name:
        conditions.append("client_name LIKE ? COLLATE NOCASE")
        params.append(f"%{client_name}%")

    if facility_name:
        conditions.append("facility_name LIKE ? COLLATE NOCASE")
        params.append(f"%{facility_name}%")

    if date_from:
        # date_generated is ISO 8601 datetime: prefix comparison works because
        # the format is lexicographically sortable.
        conditions.append("date_generated >= ?")
        params.append(date_from)

    if date_to:
        # Upper bound: include all timestamps on the date_to day by appending
        # 'T23:59:59', which is always lexicographically >= any same-day entry.
        conditions.append("date_generated <= ?")
        params.append(f"{date_to}T23:59:59")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM reports {where_clause} ORDER BY date_generated DESC"

    conn = _get_connection()
    try:
        cursor = conn.execute(sql, params)
        return [_row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_report_by_id(report_id: int) -> dict | None:
    """
    Return a single report record by its primary key.

    Parameters
    ----------
    report_id : int
        Primary key of the target record.

    Returns
    -------
    dict | None
        Record as a plain dict, or ``None`` if no matching record exists.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM reports WHERE id = ?",
            (report_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row is not None else None
    finally:
        conn.close()


def delete_report(report_id: int) -> bool:
    """
    Delete a report's database record and its associated PDF file from disk.

    Parameters
    ----------
    report_id : int
        Primary key of the record to delete.

    Returns
    -------
    bool
        ``True`` if the DB record was found and deleted (PDF may or may not
        have been present on disk — a missing file is logged as a warning but
        does not prevent success).
        ``False`` if no record with ``report_id`` exists in the database.
    """
    # Fetch the record first so we know the file_path before deleting the row
    record = get_report_by_id(report_id)
    if record is None:
        return False

    file_path = record.get("file_path", "")

    # Delete the DB record
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        conn.commit()
    finally:
        conn.close()

    # Delete the PDF from disk — resolve relative to project root
    if file_path:
        abs_path = _PROJECT_ROOT / file_path
        if abs_path.exists():
            try:
                abs_path.unlink()
            except OSError as exc:
                logger.warning(
                    "Could not delete PDF file '%s' from disk: %s",
                    abs_path,
                    exc,
                )
        else:
            logger.warning(
                "PDF file '%s' was not found on disk during deletion "
                "(DB record has been removed).",
                abs_path,
            )

    return True
