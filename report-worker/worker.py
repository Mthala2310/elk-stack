import os
import sys
import time
import argparse

from pathlib import Path

from dotenv import load_dotenv

from scheduler import (
    get_completed_hour,
    make_report_window_id,
)

from report_state import (
    is_generated,
    save_report,
    save_failure,
)

from telegram_sender import deliver_report


# =====================================
# 1. LOAD CONFIGURATION
# =====================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env")

# Gunakan modul backend yang sudah tersedia
BACKEND_DIR = PROJECT_ROOT / "backend"

sys.path.insert(0, str(BACKEND_DIR))

from app.models import TimeRange
from app.tools.validators import validate_index_pattern
from app.services.report_builder import (
    build_monitoring_report,
)


REPORT_INDEX = os.getenv(
    "REPORT_INDEX",
    "app-logs-*"
)

REPORT_TIMEZONE = os.getenv(
    "REPORT_TIMEZONE",
    "Asia/Jakarta"
)

POLL_SECONDS = int(
    os.getenv(
        "REPORT_POLL_SECONDS",
        "60"
    )
)

DB_SETTING = Path(
    os.getenv(
        "REPORT_DB_PATH",
        "state/reports.sqlite3"
    )
)

REPORT_DB = (
    DB_SETTING
    if DB_SETTING.is_absolute()
    else BASE_DIR / DB_SETTING
)

if POLL_SECONDS < 1:
    raise ValueError(
        "REPORT_POLL_SECONDS harus positif."
    )


# =====================================
# 2. GENERATE ONE COMPLETED HOUR
# =====================================

def run_one_cycle():

    # Validasi index sesuai aturan backend
    index = validate_index_pattern(
        REPORT_INDEX
    )

    # Tentukan satu jam yang sudah selesai
    start, end = get_completed_hour(
        timezone_name=REPORT_TIMEZONE
    )

    # Identitas unik periode laporan
    window_id = make_report_window_id(
        index,
        start,
        end
    )

    print(
        f"\n[REPORT] {start.isoformat()}"
        f" -> {end.isoformat()}",
        flush=True
    )

    # Jika sudah berhasil dibuat,
    # jangan generate ulang.
    if is_generated(REPORT_DB, window_id):

        print(
            "[SKIP] Report sudah GENERATED.",
            flush=True
        )

        return window_id

    try:
        # Panggil Report Builder Phase 9.3
        report = build_monitoring_report(
            index=index,
            time_range=TimeRange(
                start=start,
                end=end
            )
        )

        if report.get("report_status") not in (
            "READY", "PARTIAL"
        ):
            raise ValueError(
                "Report Builder mengembalikan "
                "status tidak dikenal."
            )

        # Simpan hasil ke SQLite
        save_report(
            db_path=REPORT_DB,
            window_id=window_id,
            index=index,
            start=start,
            end=end,
            report=report,
        )

        print(
            "[GENERATED] Report berhasil disimpan.",
            flush=True
        )

        print(
            "Total requests:",
            report["total_requests"],
            flush=True
        )

        print(
            "Report status:",
            report["report_status"],
            flush=True
        )

        if report.get("warnings"):
            print(
                "[WARNING]",
                report["warnings"],
                flush=True
            )

        return window_id

    except Exception as exc:

        error_type = type(exc).__name__

        save_failure(
            db_path=REPORT_DB,
            window_id=window_id,
            index=index,
            start=start,
            end=end,
            error_type=error_type,
        )

        print(
            f"[FAILED] {error_type}",
            flush=True
        )

        return None


# =====================================
# 3. AUTOMATIC WORKER LOOP
# =====================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--once",
        action="store_true",
        help="Jalankan satu siklus report"
    )

    args = parser.parse_args()

    print(
        "[REPORT WORKER] Starting...",
        flush=True
    )

    while True:

        # Step 9.5: Generate report
        window_id = run_one_cycle()

        if window_id is not None:

            # Step 9.7: Kirim report ke Telegram
            try:
                deliver_report(window_id)

            except Exception as exc:

                # Telegram gagal tidak boleh
                # menghentikan scheduler.
                print(
                    "[TELEGRAM REPORT ERROR]",
                    type(exc).__name__,
                    flush=True
                )

        if args.once:
            raise SystemExit(
                0 if window_id is not None else 1
            )

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
