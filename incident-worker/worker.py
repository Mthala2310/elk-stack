import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from endpoint_detector import poll_repeated_error_endpoints
from incident_store import (
    apply_incident_lifecycle,
    list_incidents,
)
from rules import RuleConfig, evaluate_rules
from stale_detector import (
    get_latest_log_timestamp,
    evaluate_stale_rule,
)
from latency_detector import poll_latency

# ==================================
# 1. LOAD CONFIGURATION DARI .ENV
# ==================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

WIB = timezone(timedelta(hours=7))

# Catat kapan proses worker mulai
WORKER_STARTED_AT = datetime.now(WIB)

# Lokasi database SQLite
INCIDENT_DB_PATH = (
    BASE_DIR / "data" / "incidents.sqlite3"
)

# Ambil seluruh konfigurasi langsung dari .env
RESOLVE_CONFIRMATIONS = int(os.getenv("INCIDENT_RESOLVE_CONFIRMATIONS", "2"))

RULE_CONFIG = RuleConfig.from_env()

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

INDEX = os.getenv("INCIDENT_INDEX", "app-logs-*")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

WINDOW_MINUTES = int(os.getenv("WINDOW_MINUTES", "5"))

REPEATED_MAX_PATHS = int(os.getenv("INCIDENT_REPEATED_MAX_PATHS", "100"))

exclude_setting = (os.getenv("INCIDENT_REPEATED_EXCLUDE_416", "true") or "").strip().lower()
if exclude_setting not in ("true", "false"):
    raise ValueError(
        "INCIDENT_REPEATED_EXCLUDE_416 harus true/false."
    )
REPEATED_EXCLUDE_416 = exclude_setting == "true"

expect_logs_value = os.getenv(
    "INCIDENT_EXPECT_LOGS", "false"
).strip().lower()
if expect_logs_value not in ("true", "false"):
    raise ValueError(
        "INCIDENT_EXPECT_LOGS harus true/false."
    )
EXPECT_LOGS = expect_logs_value == "true"

STALE_AFTER_SECONDS = int(
    os.getenv("INCIDENT_STALE_AFTER_SECONDS", "600")
)
STARTUP_GRACE_SECONDS = int(
    os.getenv("INCIDENT_STARTUP_GRACE_SECONDS", "600")
)


# ==================================
# 2. VALIDASI CONFIGURATION
# ==================================

if INDEX != "app-logs-*":
    raise ValueError("Step awal hanya mengizinkan index app-logs-*.")

if POLL_INTERVAL <= 0 or WINDOW_MINUTES <= 0:
    raise ValueError("Polling interval dan window harus positif.")


# ==================================
# 3. ELASTICSEARCH CLIENT
# ==================================

es = Elasticsearch(ES_URL, request_timeout=10)


# ==================================
# 4. POLLING FUNCTION
# ==================================


def poll_logs():
    # Waktu pemeriksaan saat ini (WIB / UTC+7)
    end = datetime.now(WIB)

    # Awal sliding window
    start = end - timedelta(minutes=WINDOW_MINUTES)

    # Filter berdasarkan timestamp
    query = {
        "range": {
            "@timestamp": {
                "gte": start.isoformat(),
                "lt": end.isoformat(),
            }
        }
    }

    # Ambil agregasi Dual-Mode (HTTP + Microservice APM) dari Elasticsearch
    result = es.search(
        index=INDEX,
        size=0,
        track_total_hits=True,
        query=query,
        aggs={
            # --- HTTP Access Log Metrics ---
            "http_events": {
                "filter": {"exists": {"field": "status_code"}}
            },
            "http_4xx": {
                "filter": {"range": {"status_code": {"gte": 400, "lt": 500}}}
            },
            "http_5xx": {
                "filter": {"range": {"status_code": {"gte": 500, "lt": 600}}}
            },
            # --- Microservice APM / Tracing Log Metrics ---
            "apm_events": {
                "filter": {
                    "bool": {
                        "should": [
                            {"exists": {"field": "log_level"}},
                            {"exists": {"field": "trace_id"}},
                            {"exists": {"field": "service_name"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            },
            "apm_error_logs": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"log_level.keyword": "ERROR"}},
                            {"term": {"log_level": "ERROR"}},
                            {"term": {"log_level": "error"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            },
            "apm_warn_logs": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"log_level.keyword": "WARN"}},
                            {"term": {"log_level": "WARN"}},
                            {"term": {"log_level": "warn"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            },
            "apm_execution_metrics": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"is_execution_metric.keyword": "true"}},
                            {"term": {"is_execution_metric": "true"}},
                            {"term": {"perf_action.keyword": "End"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            },
        },
    )

    # Hitung hasil query
    aggs = result["aggregations"]
    total = result["hits"]["total"]["value"]

    http_events = aggs["http_events"]["doc_count"]
    count_4xx = aggs["http_4xx"]["doc_count"]
    count_5xx = aggs["http_5xx"]["doc_count"]

    apm_events = aggs["apm_events"]["doc_count"]
    count_error_logs = aggs["apm_error_logs"]["doc_count"]
    count_warn_logs = aggs["apm_warn_logs"]["doc_count"]
    execution_metrics_count = aggs["apm_execution_metrics"]["doc_count"]

    if total == 0:
        schema_detected = "no_data"
    elif http_events > 0 and apm_events > 0:
        schema_detected = "hybrid"
    elif apm_events > 0:
        schema_detected = "microservice_tracing"
    elif http_events > 0:
        schema_detected = "http_access"
    else:
        schema_detected = "unknown"

    # Hindari pembagian nol
    def rate(count, denominator=None):
        denom = total if denominator is None else denominator
        if denom == 0:
            return None

        return round(count / denom * 100, 2)

    # Kembalikan hasil pemeriksaan (backward-compatible)
    return {
        "status": "NO_DATA" if total == 0 else "OBSERVED",
        "schema_detected": schema_detected,
        "index": INDEX,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "total_events": total,
        # HTTP metrics
        "http_events": http_events,
        "count_4xx": count_4xx,
        "count_5xx": count_5xx,
        "rate_4xx_percent": rate(count_4xx),
        "rate_5xx_percent": rate(count_5xx),
        # Microservice APM metrics
        "apm_events": apm_events,
        "count_error_logs": count_error_logs,
        "count_warn_logs": count_warn_logs,
        "rate_error_logs_percent": rate(count_error_logs),
        "apm_error_rate_percent": rate(count_error_logs, apm_events),
        "execution_metrics_count": execution_metrics_count,
    }


# ==================================
# 5. WORKER LOOP
# ==================================


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--once", action="store_true", help="Jalankan satu polling lalu berhenti"
    )

    args = parser.parse_args()

    print("[INCIDENT WORKER] Starting...")

    while True:
        try:
            # 1. Ambil statistik log keseluruhan (Dual-Mode: HTTP + Microservice APM)
            data = poll_logs()

            # 2. Ambil error berdasarkan endpoint
            # Menggunakan window yang sama persis.
            endpoint_data = poll_repeated_error_endpoints(
                es=es,
                index=INDEX,
                start=data["window_start"],
                end=data["window_end"],
                max_paths=REPEATED_MAX_PATHS,
                exclude_416=REPEATED_EXCLUDE_416,
            )

            # Gunakan waktu akhir polling yang sama
            reference_time = datetime.fromisoformat(
                data["window_end"]
            )
            # Jika sumber tidak diharapkan aktif,
            # tidak perlu melakukan query terbaru.
            latest_log_at = (
                get_latest_log_timestamp(es, INDEX)
                if EXPECT_LOGS
                else None
            )
            # Evaluasi kesegaran log
            stale_rule = evaluate_stale_rule(
                expected_active=EXPECT_LOGS,
                latest_event_at=latest_log_at,
                now=reference_time,
                worker_started_at=WORKER_STARTED_AT,
                stale_after_seconds=STALE_AFTER_SECONDS,
                startup_grace_seconds=STARTUP_GRACE_SECONDS,
            )

            # Ambil statistik latency dari Elasticsearch.
            # Gunakan waktu yang sama dengan rule lainnya.
            latency_data = poll_latency(
                es=es,
                index=INDEX,
                start=data["window_start"],
                end=data["window_end"],
                threshold_ms=RULE_CONFIG.latency_threshold_ms,
            )

            # 3. Evaluasi rule (termasuk stale rule)
            evaluation = evaluate_rules(
                snapshot=data,
                config=RULE_CONFIG,
                endpoint_snapshot=endpoint_data,
                stale_rule=stale_rule,
                latency_snapshot=latency_data,
            )

            # 4. Perbarui status incident pada SQLite
            incident_changes = apply_incident_lifecycle(
                evaluation=evaluation,
                db_path=INCIDENT_DB_PATH,
                confirmations=RESOLVE_CONFIRMATIONS,
            )

            # 5. Ambil riwayat incident terbaru
            incident_history = list_incidents(
                db_path=INCIDENT_DB_PATH,
                limit=10,
            )

            # 6. Susun output monitoring lengkap
            output = {
                "monitoring": data,
                "endpoint_analysis": endpoint_data,
                "latency_analysis": latency_data,
                "evaluation": evaluation,
                "incident_changes": incident_changes,
                "incident_history": incident_history,
            }

            # 7. Tampilkan hasil
            print(
                json.dumps(output, indent=2),
                flush=True,
            )

        except Exception as exc:
            print(
                json.dumps(
                    {"status": "WORKER_CYCLE_FAILED", "error_type": type(exc).__name__}
                ),
                flush=True,
            )

            # Saat test sekali, error harus
            # menyebabkan exit non-zero.
            if args.once:
                raise SystemExit(1)

        if args.once:
            break

        # Tunggu sebelum polling berikutnya
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
