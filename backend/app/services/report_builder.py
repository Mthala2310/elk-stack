from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models import TimeRange
from app.tools.validators import validate_index_pattern

from app.tools.log_summary import get_log_summary
from app.tools.top_error_paths import get_top_error_paths
from app.tools.slow_requests import get_slow_requests
from app.tools.latest_event import get_latest_event


WIB = ZoneInfo("Asia/Jakarta")


# =====================================
# 1. READ STRUCTURED TOOL RECORDS
# =====================================

def _walk_records(value, depth=0):
    """
    Membaca struktur nested dictionary/list
    dari output observability tools.
    """

    if depth > 6:
        return

    if isinstance(value, list):
        for item in value[:30]:
            yield from _walk_records(item, depth + 1)

    elif isinstance(value, dict):
        yield value

        for name in (
            "data", "results", "result", "items",
            "events", "requests", "top_paths",
            "paths", "top_error_paths",
            "slow_requests", "buckets",
            "_source", "event", "latest_event",
        ):
            if name in value:
                yield from _walk_records(
                    value[name], depth + 1
                )


def _safe_path(path):
    """
    Ambil path tanpa query string.
    Ini redaksi dasar, bukan sanitizer PII lengkap.
    """

    if not isinstance(path, str):
        return None

    if not path.startswith("/"):
        return None

    return (
        path.split("?", 1)[0]
        .split("#", 1)[0][:180]
    )


# =====================================
# 2. COMPACT TOP ERROR ENDPOINTS
# =====================================

def _top_paths(data):
    result = []

    for item in _walk_records(data):

        path = _safe_path(
            item.get("path")
            or item.get("request_path")
            or item.get("key")
        )

        count = item.get(
            "error_count",
            item.get("count", item.get("doc_count"))
        )

        if (
            path
            and type(count) is int
            and count >= 0
        ):
            result.append({
                "path": path,
                "error_count": count,
            })

    result.sort(
        key=lambda item: -item["error_count"]
    )

    return result[:5]


# =====================================
# 3. COMPACT SLOW REQUESTS
# =====================================

def _slow_samples(data):
    result = []

    for item in _walk_records(data):

        duration = item.get("response_time")

        path = _safe_path(
            item.get("request_path")
            or item.get("path")
        )

        if (
            path
            and type(duration) in (int, float)
            and duration >= 0
        ):
            result.append({
                "path": path,
                "response_time_ms": duration,
                "status_code": item.get("status_code"),
                "timestamp": item.get("@timestamp"),
            })

    result.sort(
        key=lambda item: -item["response_time_ms"]
    )

    return result[:5]


# =====================================
# 4. DATA FRESHNESS
# =====================================

def _latest_timestamp(data):

    for item in _walk_records(data):

        value = (
            item.get("@timestamp")
            or item.get("timestamp")
        )

        if not isinstance(value, str):
            continue

        try:
            dt = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

            if (
                dt.tzinfo is not None
                and dt.utcoffset() is not None
            ):
                return dt.astimezone(WIB).isoformat()

        except ValueError:
            continue

    return None


# =====================================
# 5. SHARED REPORT BUILDER
# =====================================

def build_monitoring_report(
    index: str,
    time_range: TimeRange,
) -> dict:

    # Validasi index sesuai allowlist Phase 5
    index = validate_index_pattern(index)

    start = time_range.start
    end = time_range.end

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError(
            "Periode wajib memiliki timezone."
        )

    if end <= start:
        raise ValueError(
            "Waktu akhir harus setelah waktu awal."
        )

    # Gunakan periode [start, end).
    # Dikurangi 1 mikrodetik karena beberapa
    # tool lama menggunakan lte untuk batas end.
    effective_range = TimeRange(
        start=start,
        end=end - timedelta(microseconds=1),
    )

    # Statistik utama wajib berhasil.
    # Jika gagal, jangan membuat angka rekaan.
    summary = get_log_summary(
        index=index,
        time_range=effective_range,
    )

    warnings = []

    # Tool pendukung boleh gagal secara terpisah.
    # Laporan akan diberi status PARTIAL.
    def optional_tool(name, callback):
        try:
            return callback()

        except Exception as exc:
            warnings.append(
                f"{name} gagal: {type(exc).__name__}"
            )
            return None

    # Top error endpoint
    paths_raw = optional_tool(
        "get_top_error_paths",
        lambda: get_top_error_paths(
            index=index,
            time_range=effective_range,
            error_class="all",
            limit=5,
        ),
    )

    # Top 5 request terlambat
    slow_raw = optional_tool(
        "get_slow_requests",
        lambda: get_slow_requests(
            index=index,
            time_range=effective_range,
            min_response_time=None,
            limit=5,
            offset=0,
        ),
    )

    # Event terakhir pada index secara keseluruhan
    latest_raw = optional_tool(
        "get_latest_event",
        lambda: get_latest_event(index=index),
    )

    # Ubah output menjadi struktur ringkas
    top_paths = (
        _top_paths(paths_raw)
        if paths_raw is not None else []
    )

    slow = (
        _slow_samples(slow_raw)
        if slow_raw is not None else []
    )

    latest_at = (
        _latest_timestamp(latest_raw)
        if latest_raw is not None else None
    )

    # Jangan menyembunyikan masalah struktur data.
    if (
        paths_raw is not None
        and not top_paths
        and summary["errors"]["total_errors"] > 0
    ):
        warnings.append(
            "Struktur top error paths perlu diperiksa."
        )

    if latest_raw is not None and latest_at is None:
        warnings.append(
            "Timestamp latest event belum dapat dibaca."
        )

    # Hasil report siap digunakan frontend
    # maupun Scheduled Report Worker.
    return {
        "report_type": "deterministic_monitoring",
        "index": index,

        "period": {
            "start": start.astimezone(WIB).isoformat(),
            "end": end.astimezone(WIB).isoformat(),
            "timezone": "Asia/Jakarta",
            "end_exclusive": True,
        },

        "generated_at": (
            datetime.now(timezone.utc)
            .astimezone(WIB)
            .isoformat()
        ),

        "total_requests": summary["total_events"],

        "status_classes": summary["status_classes"],

        "status_distribution": summary[
            "status_distribution"
        ],

        "errors": summary["errors"],

        "error_categories": summary.get(
            "error_categories", {}
        ),

        "top_error_endpoints": top_paths,

        "slow_request_samples": slow,

        "latest_event_in_index": latest_at,

        "response_time_unit": (
            "ms (konvensi prototype)"
        ),

        "screenshot_status": "NOT_IMPLEMENTED_YET",

        "warnings": warnings,

        "report_status": (
            "PARTIAL" if warnings else "READY"
        ),
    }
