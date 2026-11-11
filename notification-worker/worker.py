import os
import time
import json
import sqlite3
import argparse

from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from contextlib import closing

from dotenv import load_dotenv
# pyrefly: ignore[missing-import]
from telegram_client import send_telegram_message


# ====================================
# 1. CONFIGURATION
# ====================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

WIB = ZoneInfo("Asia/Jakarta")


def resolve_path(env_name, default):
    value = Path(
        os.getenv(env_name, default)
    ).expanduser()

    if not value.is_absolute():
        value = BASE_DIR / value

    return value.resolve()


INCIDENT_DB = resolve_path(
    "INCIDENT_DB_PATH",
    "../incident-worker/data/incidents.sqlite3"
)

STATE_DB = resolve_path(
    "NOTIFICATION_DB_PATH",
    "state/notifications.sqlite3"
)

POLL_SECONDS = int(
    os.getenv("NOTIFICATION_POLL_SECONDS", "10")
)

RETRY_SECONDS = int(
    os.getenv("NOTIFICATION_RETRY_SECONDS", "60")
)

MAX_ATTEMPTS = int(
    os.getenv("NOTIFICATION_MAX_ATTEMPTS", "5")
)

if min(POLL_SECONDS, RETRY_SECONDS, MAX_ATTEMPTS) < 1:
    raise ValueError(
        "Konfigurasi notification harus positif."
    )


# ====================================
# 2. SQLITE CONNECTIONS
# ====================================

def connect_state():
    STATE_DB.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row

    return conn


def connect_incidents():
    if not INCIDENT_DB.is_file():
        raise FileNotFoundError(
            "Database incident Phase 8 tidak ditemukan."
        )

    # Database incident hanya dibaca.
    uri = f"{INCIDENT_DB.as_uri()}?mode=ro"

    conn = sqlite3.connect(
        uri,
        uri=True,
        timeout=5
    )

    conn.row_factory = sqlite3.Row
    return conn


# ====================================
# 3. INITIALIZE NOTIFICATION DATABASE
# ====================================

def initialize():

    with closing(connect_incidents()) as source:
        latest = source.execute("""
            SELECT COALESCE(MAX(id), 0)
            FROM incident_events
        """).fetchone()[0]

        latest_incident = source.execute("""
            SELECT COALESCE(MAX(id), 0)
            FROM incidents
        """).fetchone()[0]

    with closing(connect_state()) as conn:

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS notification_meta (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notification_delivery (
                event_id INTEGER PRIMARY KEY,
                incident_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                telegram_message_id INTEGER,
                last_error TEXT,
                next_retry_at TEXT,
                updated_at TEXT NOT NULL
            );
        """)

        with conn:

            # Jika proses sebelumnya berhenti saat
            # request Telegram berlangsung, hasil
            # pengirimannya tidak dapat dipastikan.
            conn.execute("""
                UPDATE notification_delivery
                SET status = 'UNCERTAIN',
                    last_error = 'Interrupted during send'
                WHERE status = 'SENDING'
            """)

            # Cek apakah watermark cursor sudah ada
            row = conn.execute("""
                SELECT value FROM notification_meta
                WHERE name = 'last_processed_event_id'
            """).fetchone()

            if row is not None:
                watermark = int(row[0])
            else:
                # Migrasi baseline: cek apakah ada data lama
                old = conn.execute("""
                    SELECT value FROM notification_meta
                    WHERE name = 'start_after_event_id'
                """).fetchone()

                if old is not None:
                    sent_max = conn.execute("""
                        SELECT COALESCE(MAX(event_id), ?)
                        FROM notification_delivery
                        WHERE status = 'SENT'
                    """, (int(old[0]),)).fetchone()[0]
                    watermark = max(int(old[0]), int(sent_max))
                else:
                    watermark = int(latest)

                conn.execute("""
                    INSERT OR REPLACE INTO notification_meta (name, value)
                    VALUES ('last_processed_event_id', ?)
                """, (str(watermark),))

    return watermark, latest_incident


def save_watermark(conn, watermark):
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO notification_meta (name, value)
            VALUES ('last_processed_event_id', ?)
        """, (str(watermark),))


# ====================================
# 4. READ INCIDENT EVENTS
# ====================================

def read_events(baseline):

    # Baca dengan pagination supaya
    # setiap event baru tetap terjangkau.
    with closing(connect_incidents()) as source:

        last_id = baseline

        while True:
            rows = source.execute("""
                SELECT
                    e.id AS event_id,
                    e.incident_id,
                    e.event_type,
                    e.occurred_at,
                    e.evidence_json,
                    i.rule_id,
                    i.index_pattern
                FROM incident_events e
                JOIN incidents i
                  ON i.id = e.incident_id
                WHERE e.id > ?
                  AND e.event_type IN ('OPEN', 'RESOLVED')
                ORDER BY e.id ASC
                LIMIT 100
            """, (last_id,)).fetchall()

            if not rows:
                break

            for row in rows:
                item = dict(row)
                last_id = item["event_id"]
                yield item


# ====================================
# 5. RETRY QUEUE PROCESSING
# ====================================

def process_retries(conn):
    """
    Memeriksa dan mengirim ulang notifikasi yang
    sebelumnya gagal sementara (status RETRY).
    """
    now = datetime.now(WIB).isoformat()

    rows = conn.execute("""
        SELECT event_id
        FROM notification_delivery
        WHERE status = 'RETRY'
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
          AND attempts < ?
        ORDER BY event_id ASC
        LIMIT 10
    """, (now, MAX_ATTEMPTS)).fetchall()

    if not rows:
        return

    with closing(connect_incidents()) as source:
        for row in rows:
            event_id = row["event_id"]
            event_row = source.execute("""
                SELECT
                    e.id AS event_id,
                    e.incident_id,
                    e.event_type,
                    e.occurred_at,
                    e.evidence_json,
                    i.rule_id,
                    i.index_pattern
                FROM incident_events e
                JOIN incidents i
                  ON i.id = e.incident_id
                WHERE e.id = ?
            """, (event_id,)).fetchone()

            if event_row:
                process_event(conn, dict(event_row))


# ====================================
# 6. BUILD TELEGRAM MESSAGE
# ====================================

def to_wib(value):
    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        return dt.astimezone(WIB).strftime("%d-%m-%Y %H:%M:%S WIB")

    except (ValueError, TypeError):
        return "Waktu tidak tersedia"


def build_message(event):

    evidence = json.loads(
        event["evidence_json"]
    )

    is_open = event["event_type"] == "OPEN"

    title = (
        "🚨 INCIDENT OPEN"
        if is_open
        else "✅ INCIDENT RESOLVED"
    )

    lines = [
        title,
        "",
        f"Incident ID: #{event['incident_id']}",
        f"Rule: {event['rule_id']}",
        f"Index: {event['index_pattern']}",
        f"Event Time: {to_wib(event['occurred_at'])}",
        f"Status: {event['event_type']}",
    ]

    # Evidence RESOLVED dari SQLite merupakan
    # evidence terakhir ketika incident aktif,
    # bukan metrik pemulihan terkini.
    lines.extend([
        "",
        (
            "Evidence saat terdeteksi:"
            if is_open
            else "Evidence terakhir saat incident aktif:"
        )
    ])

    allowed_fields = {
        "window_start": "Window Start",
        "window_end": "Window End",
        "total_events": "Total Events",
        "error_count": "Error Count",
        "error_rate_percent": "Error Rate (%)",
        "p95_ms": "P95 (ms)",
        "slow_request_count": "Slow Requests",
        "age_seconds": "Log Age (seconds)",
        "reason": "Reason",
    }

    for key, label in allowed_fields.items():
        value = evidence.get(key)

        if value is not None:
            lines.append(f"{label}: {value}")

    lines.extend([
        "",
        "Buka Kibana untuk investigasi lebih lanjut."
    ])

    # Kirim ringkasan saja, bukan raw log,
    # IP, payload, atau seluruh exception.
    return "\n".join(lines)[:4000]


# ====================================
# 7. DEDUPLICATION / RESERVE EVENT
# ====================================

def reserve_event(conn, event):

    event_id = event["event_id"]

    now = datetime.now(WIB)
    now_text = now.isoformat()

    with conn:

        row = conn.execute("""
            SELECT status, attempts, next_retry_at
            FROM notification_delivery
            WHERE event_id = ?
        """, (event_id,)).fetchone()

        if row is None:

            conn.execute("""
                INSERT INTO notification_delivery (
                    event_id,
                    incident_id,
                    event_type,
                    status,
                    attempts,
                    updated_at
                )
                VALUES (?, ?, ?, 'SENDING', 1, ?)
            """, (
                event_id,
                event["incident_id"],
                event["event_type"],
                now_text,
            ))

            return 1

        # Hanya event RETRY yang boleh
        # dicoba kembali secara otomatis.
        if row["status"] != "RETRY":
            return None

        attempts = row["attempts"]

        if attempts >= MAX_ATTEMPTS:
            conn.execute("""
                UPDATE notification_delivery
                SET status = 'FAILED_FINAL'
                WHERE event_id = ?
            """, (event_id,))
            return None

        if row["next_retry_at"]:
            due = datetime.fromisoformat(
                row["next_retry_at"]
            )

            if now < due:
                return None

        attempts += 1

        conn.execute("""
            UPDATE notification_delivery
            SET status = 'SENDING',
                attempts = ?,
                updated_at = ?
            WHERE event_id = ?
        """, (attempts, now_text, event_id))

        return attempts


# ====================================
# 8. SAVE DELIVERY RESULT
# ====================================

def save_result(
    conn,
    event_id,
    status,
    message_id=None,
    error=None,
    next_retry_at=None,
):

    with conn:
        conn.execute("""
            UPDATE notification_delivery
            SET status = ?,
                telegram_message_id = ?,
                last_error = ?,
                next_retry_at = ?,
                updated_at = ?
            WHERE event_id = ?
        """, (
            status,
            message_id,
            error,
            next_retry_at,
            datetime.now(WIB).isoformat(),
            event_id,
        ))


# ====================================
# 9. FAILURE CLASSIFICATION
# ====================================

def classify_failure(exc):

    message = str(exc)

    # 429: Telegram menolak request karena
    # rate limit. Bisa dicoba ulang.
    if "Telegram HTTP 429" in message:
        return "RETRY"

    # Connection belum berhasil dibangun.
    if "ConnectTimeout" in message:
        return "RETRY"

    # Request tidak valid atau akses ditolak.
    if any(
        f"Telegram HTTP {code}" in message
        for code in (400, 401, 403, 404)
    ):
        return "FAILED_FINAL"

    # ReadTimeout, putus koneksi, atau
    # response tak pasti: jangan otomatis
    # kirim ulang karena bisa sudah terkirim.
    return "UNCERTAIN"


# ====================================
# 10. PROCESS ONE EVENT
# ====================================

def process_event(conn, event):

    event_id = event["event_id"]

    attempt = reserve_event(conn, event)

    # SENT, UNCERTAIN, FAILED_FINAL,
    # atau RETRY yang belum waktunya.
    if attempt is None:
        return

    try:
        message = build_message(event)

        response = send_telegram_message(message)

        save_result(
            conn,
            event_id,
            "SENT",
            message_id=response.get("message_id"),
        )

        incident_id = event.get("incident_id")
        print(
            f"[SENT] Event #{event_id} (Incident #{incident_id}) "
            f"{event['event_type']}",
            flush=True,
        )

    except Exception as exc:

        state = classify_failure(exc)

        retry_at = None

        if state == "RETRY":

            if attempt >= MAX_ATTEMPTS:
                state = "FAILED_FINAL"

            else:
                delay = min(
                    RETRY_SECONDS * (2 ** (attempt - 1)),
                    1800
                )

                retry_at = (
                    datetime.now(WIB)
                    + timedelta(seconds=delay)
                ).isoformat()

        # Catat jenis kegagalan tanpa
        # menyimpan URL/API token.
        error_text = (
            f"{type(exc).__name__}: "
            f"{str(exc)[:100]}"
        )

        save_result(
            conn,
            event_id,
            state,
            error=error_text,
            next_retry_at=retry_at,
        )

        incident_id = event.get("incident_id")
        print(
            f"[{state}] Event #{event_id} (Incident #{incident_id})",
            flush=True,
        )


# ====================================
# 11. WORKER LOOP
# ====================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--once",
        action="store_true",
        help="Periksa event satu kali"
    )

    args = parser.parse_args()

    # Membaca watermark terkini dan menyiapkan
    # tabel status pengiriman.
    watermark, latest_incident = initialize()

    print(
        "[NOTIFICATION WORKER] Started",
        flush=True
    )
    print(
        f"Monitoring events after Event #{watermark} (Latest Incident #{latest_incident})",
        flush=True
    )

    with closing(connect_state()) as conn:

        while True:

            try:
                # 1. Jalur event baru: hanya membaca event di atas watermark
                for event in read_events(watermark):
                    process_event(conn, event)

                    if event["event_id"] > watermark:
                        watermark = event["event_id"]
                        save_watermark(conn, watermark)

                # 2. Jalur retry khusus: jika ada notifikasi gagal sementara
                process_retries(conn)

            except Exception as exc:

                # Kegagalan notifier tidak boleh
                # menghentikan Incident Worker.
                print(
                    "[NOTIFICATION ERROR]",
                    type(exc).__name__,
                    flush=True
                )

                if args.once:
                    raise SystemExit(1)

            if args.once:
                break

            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
