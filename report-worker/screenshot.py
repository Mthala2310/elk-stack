
import os
import argparse
import hashlib
import sqlite3

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import (
    urlsplit,
    urlunsplit,
    parse_qsl,
    urlencode,
)
from contextlib import closing

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


# ====================================
# 1. CONFIGURATION
# ====================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "state" / "reports.sqlite3"

DASHBOARD_URL = os.getenv(
    "KIBANA_DASHBOARD_URL", ""
).strip()

SCREENSHOT_DIR = BASE_DIR / os.getenv(
    "REPORT_SCREENSHOT_DIR",
    "state/screenshots"
)

AUTH_FILE = BASE_DIR / "state" / "kibana-auth.json"

READY_SELECTOR = (
    '[data-test-subj="dashboardViewport"],'
    '[data-test-subj="dashboardGrid"],'
    '[data-test-subj="dashboardPanel"],'
    '[data-test-subj^="embeddablePanel"]'
)


# ====================================
# 2. GET LATEST GENERATED REPORT
# ====================================

def get_latest_report():

    if not DB_PATH.exists():
        raise FileNotFoundError(
            "reports.sqlite3 belum tersedia."
        )

    with closing(sqlite3.connect(DB_PATH)) as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT
                window_id,
                index_pattern,
                window_start,
                window_end
            FROM report_runs
            WHERE status = 'GENERATED'
            ORDER BY window_end DESC
            LIMIT 1
        """).fetchone()

    if row is None:
        raise ValueError(
            "Belum ada report GENERATED."
        )

    return dict(row)


# ====================================
# 3. SET KIBANA TIME RANGE
# ====================================

def make_dashboard_url(
    base_url: str,
    start: str,
    end: str,
):

    parsed = urlsplit(base_url)

    # Prototype hanya mengizinkan
    # Kibana lokal pada port 5601.
    if (
        parsed.scheme != "http"
        or parsed.hostname not in (
            "localhost", "127.0.0.1"
        )
        or parsed.port != 5601
        or "/app/dashboards" not in parsed.path
    ):
        raise ValueError(
            "Gunakan URL dashboard Kibana lokal "
            "http://localhost:5601/app/dashboards..."
        )

    # Pastikan berasal dari saved dashboard,
    # bukan short URL atau dashboard listing.
    if "/view/" not in base_url:
        raise ValueError(
            "Gunakan direct link saved dashboard."
        )

    def to_utc_iso(value):
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            raise ValueError(
                "Timestamp laporan wajib memiliki timezone."
            )

        return dt.astimezone(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    start_utc = to_utc_iso(start)
    end_utc = to_utc_iso(end)

    # _g adalah global state Kibana,
    # termasuk filter rentang waktu.
    global_state = (
        "(time:("
        f"from:'{start_utc}',"
        f"to:'{end_utc}'"
        "),refreshInterval:(pause:!t,value:0))"
    )

    # Link Kibana sering menaruh query
    # di belakang tanda #.
    if "?" in parsed.fragment:

        route, query = parsed.fragment.split("?", 1)

        params = [
            (k, v)
            for k, v in parse_qsl(query)
            if k != "_g"
        ]

        params.append(("_g", global_state))

        updated_fragment = (
            route + "?" + urlencode(params)
        )

        return urlunsplit(
            parsed._replace(
                fragment=updated_fragment
            )
        )

    # Jika fragment ada tetapi belum memiliki
    # query, tambahkan _g di dalam fragment.
    if parsed.fragment:

        return urlunsplit(
            parsed._replace(
                fragment=(
                    parsed.fragment
                    + "?"
                    + urlencode({"_g": global_state})
                )
            )
        )

    # Dashboard URL tanpa fragment
    params = [
        (k, v)
        for k, v in parse_qsl(parsed.query)
        if k != "_g"
    ]

    params.append(("_g", global_state))

    return urlunsplit(
        parsed._replace(
            query=urlencode(params)
        )
    )


# ====================================
# 4. CAPTURE SCREENSHOT
# ====================================

def capture_dashboard(url, output_path):

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        try:
            options = {
                "viewport": {
                    "width": 1600,
                    "height": 1000,
                },
                "device_scale_factor": 1,
                "timezone_id": "Asia/Jakarta",
                "locale": "id-ID",
            }

            # Gunakan sesi login tersimpan
            # apabila Kibana memerlukan autentikasi.
            if AUTH_FILE.is_file():
                options["storage_state"] = str(
                    AUTH_FILE
                )

            context = browser.new_context(**options)
            page = context.new_page()

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if (
                response is not None
                and response.status >= 400
            ):
                raise RuntimeError(
                    "Dashboard mengembalikan HTTP error."
                )

            # Jangan menyimpan halaman login
            # sebagai screenshot laporan.
            if page.locator(
                'input[type="password"]'
            ).count():
                raise RuntimeError(
                    "Kibana membutuhkan login."
                )

            # Tunggu elemen dashboard terlihat.
            page.wait_for_selector(
                READY_SELECTOR,
                state="visible",
                timeout=60000,
            )

            # Tunggu komponen yang secara eksplisit
            # melaporkan render belum selesai.
            if page.locator(
                '[data-render-complete="false"]'
            ).count():

                page.wait_for_function(
                    """() => !document.querySelector(
                        '[data-render-complete="false"]'
                    )""",
                    timeout=60000,
                )

            # Simpan screenshot dashboard
            page.screenshot(
                path=str(output_path),
                full_page=True,
                animations="disabled",
            )

            context.close()

        finally:
            browser.close()


# ====================================
# 5. SAVE SCREENSHOT STATUS
# ====================================

def save_status(window_id, status, path=None, error=None):

    with closing(sqlite3.connect(DB_PATH)) as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS report_screenshots (
                window_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                file_path TEXT,
                last_error TEXT,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            INSERT INTO report_screenshots (
                window_id,
                status,
                file_path,
                last_error,
                updated_at
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
            str(path) if path else None,
            error,
            datetime.now(
                timezone.utc
            ).isoformat(),
        ))

        conn.commit()


# ====================================
# 6. MAIN
# ====================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Periksa periode tanpa membuka browser"
    )

    args = parser.parse_args()

    report = get_latest_report()

    target_url = make_dashboard_url(
        DASHBOARD_URL,
        report["window_start"],
        report["window_end"],
    )

    print("Index:", report["index_pattern"])
    print("Start:", report["window_start"])
    print("End  :", report["window_end"])

    if args.dry_run:
        print("PASS: Screenshot configuration ready.")
        return

    # Nama file aman dari karakter khusus URL
    identifier = hashlib.sha256(
        report["window_id"].encode("utf-8")
    ).hexdigest()[:16]

    output = SCREENSHOT_DIR / (
        f"dashboard_{identifier}.png"
    )

    try:
        capture_dashboard(
            target_url,
            output,
        )

        save_status(
            report["window_id"],
            "CAPTURED",
            path=output,
        )

        print("[CAPTURED]", output)

    except Exception as exc:

        # Catat jenis error, tidak menyimpan
        # URL yang mungkin memuat detail internal.
        save_status(
            report["window_id"],
            "FAILED",
            error=type(exc).__name__,
        )

        print(
            "[SCREENSHOT FAILED]",
            type(exc).__name__,
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()
