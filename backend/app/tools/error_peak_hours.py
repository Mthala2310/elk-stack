from datetime import datetime, timedelta, timezone
from typing import Any

from app.es_client import get_es_client
from app.models import TimeRange
from app.tools.error_rules import (
    BUSINESS_4XX,
    TECHNICAL_4XX,
)
from app.tools.validators import validate_index_pattern

WIB = timezone(timedelta(hours=7))

ALLOWED_CATEGORIES = {
    "all_errors",
    "technical_4xx",
    "business_4xx",
    "server_5xx",
    "unclassified_4xx",
    "error_logs",
}


def build_error_filter(
    category: str,
    status_code: int | None,
) -> dict:
    if category not in ALLOWED_CATEGORIES:
        raise ValueError("Kategori error tidak dikenal.")

    if status_code is not None:
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 400 <= status_code <= 599
        ):
            raise ValueError(
                "status_code harus berupa integer antara 400 dan 599."
            )

        if category != "all_errors":
            raise ValueError(
                "status_code hanya dapat digunakan dengan category all_errors."
            )

        return {"term": {"status_code": status_code}}

    if category == "technical_4xx":
        return {"terms": {"status_code": sorted(TECHNICAL_4XX)}}

    if category == "business_4xx":
        return {"terms": {"status_code": sorted(BUSINESS_4XX)}}

    if category == "server_5xx":
        return {"range": {"status_code": {"gte": 500, "lt": 600}}}

    if category == "unclassified_4xx":
        return {
            "bool": {
                "filter": [
                    {"range": {"status_code": {"gte": 400, "lt": 500}}}
                ],
                "must_not": [
                    {
                        "terms": {
                            "status_code": sorted(
                                TECHNICAL_4XX | BUSINESS_4XX
                            )
                        }
                    }
                ],
            }
        }

    if category == "error_logs":
        return {
            "bool": {
                "should": [
                    {"term": {"log_level.keyword": "ERROR"}},
                    {"term": {"log_level": "ERROR"}},
                    {"term": {"log_level": "error"}},
                ],
                "minimum_should_match": 1,
            }
        }

    # all_errors (Dual-Mode: HTTP 4xx-5xx ATAU Log Level ERROR)
    return {
        "bool": {
            "should": [
                {"range": {"status_code": {"gte": 400, "lt": 600}}},
                {"term": {"log_level.keyword": "ERROR"}},
                {"term": {"log_level": "ERROR"}},
                {"term": {"log_level": "error"}},
            ],
            "minimum_should_match": 1,
        }
    }


def get_error_peak_hours(
    index: str,
    time_range: TimeRange,
    category: str = "all_errors",
    status_code: int | None = None,
    path: str | None = None,
    service_name: str | None = None,
    window_hours: int = 1,
) -> dict:
    index = validate_index_pattern(index)

    if window_hours not in {1, 2, 3}:
        raise ValueError("window_hours harus bernilai 1, 2, atau 3.")

    error_filter = build_error_filter(category, status_code)

    es = get_es_client()

    filters: list[dict[str, Any]] = [
        {
            "range": {
                "@timestamp": {
                    "gte": time_range.start.isoformat(),
                    "lte": time_range.end.isoformat(),
                }
            }
        }
    ]

    if path is not None:
        filters.append({
            "bool": {
                "should": [
                    {"match": {"request_path": path}},
                    {"match": {"service_name": path}},
                ],
                "minimum_should_match": 1,
            }
        })

    if service_name is not None:
        filters.append({
            "bool": {
                "should": [
                    {"term": {"service_name.keyword": service_name}},
                    {"match": {"service_name": service_name}},
                ],
                "minimum_should_match": 1,
            }
        })

    query: dict[str, Any] = {"bool": {"filter": filters}}

    aggs = {
        "hourly": {
            "date_histogram": {
                "field": "@timestamp",
                "fixed_interval": "1h",
                "time_zone": "+07:00",
                "min_doc_count": 0,
                "extended_bounds": {
                    "min": time_range.start.isoformat(),
                    "max": time_range.end.isoformat(),
                },
            },
            "aggs": {
                "error_count": {
                    "filter": error_filter
                }
            },
        }
    }

    result = es.search(
        index=index,
        size=0,
        query=query,
        aggs=aggs,
    )

    buckets = result["aggregations"]["hourly"]["buckets"]

    hourly_data = []
    for bucket in buckets:
        start = datetime.fromisoformat(bucket["key_as_string"])
        end = start + timedelta(hours=1)

        # Hanya sertakan jam utuh yang berada dalam batas time_range
        if start < time_range.start or end > time_range.end:
            continue

        total = bucket["doc_count"]
        error_count = bucket["error_count"]["doc_count"]
        rate = (
            round(error_count / total * 100, 2)
            if total > 0
            else 0.0
        )

        hourly_data.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total_events": total,
            "error_count": error_count,
            "error_rate_percent": rate,
            "_dt_start": start,
            "_dt_end": end,
        })

    windows = []
    for i in range(len(hourly_data) - window_hours + 1):
        chunk = hourly_data[i : i + window_hours]

        # Pastikan jendela terdiri dari jam-jam berurutan
        if chunk[-1]["_dt_end"] - chunk[0]["_dt_start"] != timedelta(hours=window_hours):
            continue

        w_total = sum(h["total_events"] for h in chunk)
        w_error = sum(h["error_count"] for h in chunk)
        w_rate = (
            round(w_error / w_total * 100, 2)
            if w_total > 0
            else 0.0
        )

        windows.append({
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "total_events": w_total,
            "error_count": w_error,
            "error_rate_percent": w_rate,
        })

    # Urutkan berdasarkan jumlah error terbanyak.
    # Jika sama, pilih jam yang lebih awal.
    ranked_windows = sorted(
        [
            w for w in windows
            if w["error_count"] > 0
        ],
        key=lambda w: (
            -w["error_count"],
            w["start"],
        ),
    )

    total_matching_errors = sum(
        h["error_count"] for h in hourly_data
    )

    return {
        "index": index,
        "time_range": {
            "start": time_range.start.isoformat(),
            "end": time_range.end.isoformat(),
        },
        "timezone": "Asia/Jakarta (+07:00)",
        "window_hours": window_hours,
        "filter": {
            "category": category,
            "status_code": status_code,
            "path": path,
            "service_name": service_name,
        },
        "total_matching_errors": total_matching_errors,
        "peak_time_range": (
            ranked_windows[0]
            if ranked_windows
            else None
        ),
        "top_time_ranges": ranked_windows[:5],
    }
