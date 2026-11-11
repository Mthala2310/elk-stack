
import json
import sqlite3

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def connect_db(db_path):
    path = Path(db_path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        path,
        timeout=10
    )

    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_runs (
            window_id TEXT PRIMARY KEY,
            index_pattern TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            report_json TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    return conn


def is_generated(db_path, window_id):
    """
    True jika laporan untuk periode ini
    sudah berhasil dibuat sebelumnya.
    """

    with closing(connect_db(db_path)) as conn:
        row = conn.execute("""
            SELECT status
            FROM report_runs
            WHERE window_id = ?
        """, (window_id,)).fetchone()

        return (
            row is not None
            and row["status"] == "GENERATED"
        )


def save_report(
    db_path,
    window_id,
    index,
    start,
    end,
    report,
):
    """
    Simpan laporan yang berhasil dibuat.
    """

    with closing(connect_db(db_path)) as conn:
        with conn:
            conn.execute("""
                INSERT INTO report_runs (
                    window_id,
                    index_pattern,
                    window_start,
                    window_end,
                    status,
                    attempts,
                    report_json,
                    last_error,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'GENERATED', 1, ?, NULL, ?)

                ON CONFLICT(window_id)
                DO UPDATE SET
                    status = 'GENERATED',
                    attempts = report_runs.attempts + 1,
                    report_json = excluded.report_json,
                    last_error = NULL,
                    updated_at = excluded.updated_at
            """, (
                window_id,
                index,
                start.isoformat(),
                end.isoformat(),
                json.dumps(
                    report,
                    ensure_ascii=False
                ),
                utc_now(),
            ))


def save_failure(
    db_path,
    window_id,
    index,
    start,
    end,
    error_type,
):
    """
    Catat kegagalan tanpa menyimpan
    detail rahasia atau raw exception.
    """

    with closing(connect_db(db_path)) as conn:
        with conn:
            conn.execute("""
                INSERT INTO report_runs (
                    window_id,
                    index_pattern,
                    window_start,
                    window_end,
                    status,
                    attempts,
                    last_error,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'FAILED', 1, ?, ?)

                ON CONFLICT(window_id)
                DO UPDATE SET
                    status = 'FAILED',
                    attempts = report_runs.attempts + 1,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
            """, (
                window_id,
                index,
                start.isoformat(),
                end.isoformat(),
                error_type,
                utc_now(),
            ))
