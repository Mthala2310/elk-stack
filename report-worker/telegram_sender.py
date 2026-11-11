
import os
import sys
import json
import hashlib
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import closing

import requests
from dotenv import load_dotenv

from screenshot import (
    make_dashboard_url,
    capture_dashboard,
    DASHBOARD_URL, 
    SCREENSHOT_DIR,
)


BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env")

# Pakai Telegram client yang sudah dibuat
# pada Phase 9.1.
sys.path.insert(
    0, str(ROOT / "notification-worker")
)

from telegram_client import send_telegram_message


DB_SETTING = Path(
    os.getenv(
        "REPORT_DB_PATH",
        "state/reports.sqlite3"
    )
)

REPORT_DB = (
    DB_SETTING if DB_SETTING.is_absolute()
    else BASE_DIR / DB_SETTING
)

SEND_SCREENSHOT = os.getenv(
    "REPORT_SEND_SCREENSHOT", "false"
).lower() == "true"
INCLUDE_PATHS = os.getenv(
    "REPORT_INCLUDE_ENDPOINT_PATHS", "false"
).lower() == "true"

RETRY_SECONDS = int(
    os.getenv("REPORT_TELEGRAM_RETRY_SECONDS", "90")
)

MAX_ATTEMPTS = int(
    os.getenv("REPORT_TELEGRAM_MAX_ATTEMPTS", "5")
)


def utc_now():
    return datetime.now(timezone.utc)


# =====================================
# 1. DATABASE & DELIVERY STATE
# =====================================

def connect_db():

    if not REPORT_DB.is_file():
        raise FileNotFoundError(
            "Database report belum tersedia."
        )

    conn = sqlite3.connect(REPORT_DB, timeout=10)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS report_deliveries (
            window_id TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'PENDING',
            text_message_id INTEGER,
            photo_message_id INTEGER,
            text_attempts INTEGER NOT NULL DEFAULT 0,
            photo_attempts INTEGER NOT NULL DEFAULT 0,
            next_retry_at TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS report_screenshots (
            window_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            file_path TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        );
    """)

    # Jika proses sebelumnya berhenti ketika
    # mengirim, hasilnya belum dapat dipastikan.
    with conn:
        conn.execute("""
            UPDATE report_deliveries
            SET state = 'UNCERTAIN_TEXT'
            WHERE state = 'SENDING_TEXT'
        """)

        conn.execute("""
            UPDATE report_deliveries
            SET state = 'UNCERTAIN_PHOTO'
            WHERE state = 'SENDING_PHOTO'
        """)

    return conn


def set_state(
    conn, window_id, state,
    error=None, retry_at=None,
    text_id=None, photo_id=None,
):

    with conn:
        conn.execute("""
            UPDATE report_deliveries
            SET state = ?,
                last_error = ?,
                next_retry_at = ?,
                text_message_id = COALESCE(
                    ?, text_message_id
                ),
                photo_message_id = COALESCE(
                    ?, photo_message_id
                ),
                updated_at = ?
            WHERE window_id = ?
        """, (
            state,
            error,
            retry_at,
            text_id,
            photo_id,
            utc_now().isoformat(),
            window_id,
        ))


def mark_sending(conn, window_id, part):

    field = (
        "text_attempts"
        if part == "TEXT"
        else "photo_attempts"
    )

    # Nama field hanya berasal dari pilihan
    # internal di atas, bukan input pengguna.
    with conn:
        conn.execute(f"""
            UPDATE report_deliveries
            SET state = ?,
                {field} = {field} + 1,
                updated_at = ?
            WHERE window_id = ?
        """, (
            f"SENDING_{part}",
            utc_now().isoformat(),
            window_id,
        ))


# =====================================
# 2. FORMAT LAPORAN
# =====================================

def build_report_text(report, screenshot_ready):

    period = report["period"]
    statuses = report.get("status_classes", {})
    errors = report.get("errors", {})

    lines = [
        "📊 HOURLY MONITORING REPORT",
        "",
        f"Index: {report['index']}",
        f"Start: {period['start']}",
        f"End: {period['end']}",
        "",
        f"Total Requests: {report['total_requests']:,}",
        f"HTTP 2xx: {statuses.get('2xx', 0):,}",
        f"HTTP 3xx: {statuses.get('3xx', 0):,}",
        f"HTTP 4xx: {statuses.get('4xx', 0):,}",
        f"HTTP 5xx: {statuses.get('5xx', 0):,}",
        "",
        (
            "Error Rate: "
            f"{errors.get('error_rate_percent', 0)}%"
        ),
        (
            "4xx Rate: "
            f"{errors.get('client_error_rate_percent', 0)}%"
        ),
        (
            "5xx Rate: "
            f"{errors.get('server_error_rate_percent', 0)}%"
        ),
        "",
        "Top Error Endpoints:",
    ]

    top_paths = report.get(
        "top_error_endpoints", []
    )

    if not top_paths:
        lines.append("- Tidak tersedia")

    else:
        for item in top_paths[:5]:
            count = item["error_count"]

            if INCLUDE_PATHS:
                path = item["path"]
                lines.append(
                    f"- {path[:120]}: {count} errors"
                )
            else:
                lines.append(
                    f"- {count} errors (path disembunyikan)"
                )

    lines.extend([
        "",
        "Slow Requests:",
    ])

    slow = report.get("slow_request_samples", [])

    if not slow:
        lines.append("- Tidak tersedia")
    else:
        for item in slow[:3]:
            lines.append(
                f"- {item['response_time_ms']} ms"
            )

    lines.extend([
        "",
        (
            "Latest Event: "
            f"{report.get('latest_event_in_index') or '-'}"
        ),
        f"Report Status: {report['report_status']}",
        (
            "Screenshot: Dilampirkan"
            if screenshot_ready
            else "Screenshot: Tidak tersedia"
        ),
    ])

    if report.get("warnings"):
        lines.append("")
        lines.append(
            "Catatan: Sebagian data laporan tidak lengkap."
        )

    # Telegram membatasi panjang pesan teks.
    return "\n".join(lines)[:4000]


# =====================================
# 3. SCREENSHOT FOR EXACT REPORT WINDOW
# =====================================

def ensure_screenshot(conn, row):

    window_id = row["window_id"]

    if not SEND_SCREENSHOT:
        return None, "DISABLED"

    identifier = hashlib.sha256(
        window_id.encode("utf-8")
    ).hexdigest()[:16]

    output = SCREENSHOT_DIR / (
        f"dashboard_{identifier}.png"
    )

    existing = conn.execute("""
        SELECT status FROM report_screenshots
        WHERE window_id = ?
    """, (window_id,)).fetchone()

    if (
        existing
        and existing["status"] == "CAPTURED"
        and output.is_file()
    ):
        return output, "CAPTURED"

    try:
        target = make_dashboard_url(
            DASHBOARD_URL,
            row["window_start"],
            row["window_end"],
        )

        capture_dashboard(target, output)

        # Telegram sendPhoto menerima upload
        # PNG hingga 10 MB.
        if output.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("PHOTO_TOO_LARGE")

        status = "CAPTURED"
        error = None

    except Exception as exc:
        status = "FAILED"
        error = type(exc).__name__
        output = None

    with conn:
        conn.execute("""
            INSERT INTO report_screenshots (
                window_id, status, file_path,
                last_error, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(window_id)
            DO UPDATE SET
                status = excluded.status,
                file_path = excluded.file_path,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
        """, (
            window_id,
            status,
            str(output) if output else None,
            error,
            utc_now().isoformat(),
        ))

    return output, status


# =====================================
# 4. UPLOAD PHOTO TO TELEGRAM
# =====================================

def send_telegram_photo(path, caption):

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        raise ValueError(
            "Konfigurasi Telegram belum tersedia."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendPhoto"
    )

    try:
        with open(path, "rb") as photo:
            response = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "caption": caption[:1024],
                },
                files={
                    "photo": (
                        "dashboard.png",
                        photo,
                        "image/png",
                    )
                },
                timeout=(5, 30),
            )

    except requests.RequestException as exc:
        # Jangan membocorkan URL berisi token
        raise RuntimeError(
            f"Telegram connection: {type(exc).__name__}"
        ) from None

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram HTTP {response.status_code}"
        )

    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            "Telegram invalid JSON"
        ) from None

    if not result.get("ok"):
        raise RuntimeError("Telegram rejected photo")

    return result["result"]


# =====================================
# 5. FAILURE HANDLING
# =====================================

def handle_delivery_error(
    conn, window_id, part, attempts, exc
):

    error = str(exc)

    if (
        "Telegram HTTP 429" in error
        or "ConnectTimeout" in error
    ):
        if attempts >= MAX_ATTEMPTS:
            state = f"FAILED_{part}"
            retry_at = None
        else:
            state = f"RETRY_{part}"
            retry_at = (
                utc_now()
                + timedelta(seconds=RETRY_SECONDS)
            ).isoformat()

    elif any(
        f"Telegram HTTP {code}" in error
        for code in (400, 401, 403, 404)
    ):
        state = f"FAILED_{part}"
        retry_at = None

    else:
        # Respons tidak pasti. Jangan
        # retry otomatis agar tidak spam.
        state = f"UNCERTAIN_{part}"
        retry_at = None

    set_state(
        conn, window_id, state,
        error=type(exc).__name__,
        retry_at=retry_at,
    )

    print(
        f"[{state}] Report: {window_id}",
        flush=True
    )


# =====================================
# 6. DELIVER ONE REPORT
# =====================================

def deliver_report(window_id):

    with closing(connect_db()) as conn:

        row = conn.execute("""
            SELECT * FROM report_runs
            WHERE window_id = ?
              AND status = 'GENERATED'
        """, (window_id,)).fetchone()

        if row is None:
            print("[SKIP] Report belum GENERATED.")
            return

        conn.execute("""
            INSERT OR IGNORE INTO report_deliveries (
                window_id, state, updated_at
            )
            VALUES (?, 'PENDING', ?)
        """, (window_id, utc_now().isoformat()))
        conn.commit()

        delivery = conn.execute("""
            SELECT * FROM report_deliveries
            WHERE window_id = ?
        """, (window_id,)).fetchone()

        state = delivery["state"]

        terminal_states = {
            "SENT", "SENT_TEXT_ONLY",
            "FAILED_TEXT", "FAILED_PHOTO",
            "UNCERTAIN_TEXT", "UNCERTAIN_PHOTO",
        }

        if state in terminal_states:
            print(f"[SKIP] Delivery state: {state}")
            return

        if state.startswith("RETRY_"):
            due = delivery["next_retry_at"]

            if due and utc_now() < datetime.fromisoformat(due):
                print("[SKIP] Menunggu waktu retry.")
                return

        # 1. Pastikan screenshot periode ini
        screenshot, screenshot_status = (
            ensure_screenshot(conn, row)
        )

        report = json.loads(row["report_json"])

        # 2. Kirim teks sekali
        if state in ("PENDING", "RETRY_TEXT"):

            message = build_report_text(
                report,
                screenshot_ready=screenshot is not None,
            )

            mark_sending(conn, window_id, "TEXT")

            try:
                result = send_telegram_message(message)

                set_state(
                    conn, window_id, "TEXT_SENT",
                    text_id=result.get("message_id"),
                )

                print("[TEXT SENT]", window_id)

            except Exception as exc:

                latest = conn.execute("""
                    SELECT text_attempts
                    FROM report_deliveries
                    WHERE window_id = ?
                """, (window_id,)).fetchone()

                handle_delivery_error(
                    conn, window_id, "TEXT",
                    latest["text_attempts"], exc,
                )
                return

        # 3. Jika screenshot gagal,
        # teks tetap dianggap terkirim.
        if screenshot is None:

            set_state(
                conn, window_id,
                "SENT_TEXT_ONLY",
                error=f"Screenshot: {screenshot_status}",
            )

            print("[SENT TEXT ONLY]", window_id)
            return

        # 4. Kirim screenshot
        mark_sending(conn, window_id, "PHOTO")

        try:
            result = send_telegram_photo(
                screenshot,
                "📸 Kibana Dashboard — Hourly Report",
            )

            set_state(
                conn, window_id, "SENT",
                photo_id=result.get("message_id"),
            )

            print("[REPORT SENT]", window_id)

        except Exception as exc:

            latest = conn.execute("""
                SELECT photo_attempts
                FROM report_deliveries
                WHERE window_id = ?
            """, (window_id,)).fetchone()

            handle_delivery_error(
                conn, window_id, "PHOTO",
                latest["photo_attempts"], exc,
            )


# =====================================
# 7. COMMAND LINE
# =====================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--preview",
        action="store_true"
    )

    parser.add_argument(
        "--send-latest",
        action="store_true"
    )

    args = parser.parse_args()

    with closing(connect_db()) as conn:
        row = conn.execute("""
            SELECT * FROM report_runs
            WHERE status = 'GENERATED'
            ORDER BY window_end DESC
            LIMIT 1
        """).fetchone()

        if row is None:
            raise SystemExit(
                "Belum ada report GENERATED."
            )

        window_id = row["window_id"]

        if args.preview:
            report = json.loads(row["report_json"])
            print(build_report_text(report, False))

        elif args.send_latest:
            pass

        else:
            parser.error(
                "Gunakan --preview atau --send-latest."
            )

    if args.send_latest:
        deliver_report(window_id)


if __name__ == "__main__":
    main()
