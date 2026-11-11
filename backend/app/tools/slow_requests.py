from typing import Any
from app.es_client import get_es_client
from app.models import TimeRange

from app.tools.validators import (
    validate_index_pattern,
    validate_limit,
)

SOURCE_FIELDS = [
    "@timestamp",
    # HTTP Fields
    "ip_addr",
    "http_method",
    "request_path",
    "http_version",
    "status_code",
    "request_size",
    "response_time",
    "user_agent",
    # Microservice APM / Tracing Fields
    "trace_id",
    "service_name",
    "service_version",
    "step_name",
    "perf_action",
    "duration_ms",
    "is_execution_metric",
    "caller_class",
    "caller_method",
    "caller_line",
    "log_level",
    "message",
]


def get_slow_requests(
    index: str,
    time_range: TimeRange,
    min_response_time: float | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict:

    index = validate_index_pattern(index)
    limit = validate_limit(limit)

    if offset < 0:
        raise ValueError("offset tidak boleh negatif")

    if min_response_time is not None and min_response_time < 0:
        raise ValueError("min_response_time tidak boleh negatif")

    es = get_es_client()

    # 1. Filter rentang waktu dasar
    filters: list[dict[str, Any]] = [
        {
            "range": {
                "@timestamp": {
                    "gte": time_range.start.isoformat(),
                    "lte": time_range.end.isoformat(),
                }
            }
        },
        # Cari dokumen yang memiliki salah satu metrik latensi valid:
        # 1. HTTP Lama: memiliki field response_time
        # 2. Microservice Baru: memiliki duration_ms DAN (is_execution_metric="true" atau perf_action="End")
        #    Penting: Baris 'Start' (misal Start [29998 ms]) adalah sisa timeout budget, BUKAN durasi eksekusi!
        {
            "bool": {
                "should": [
                    {"exists": {"field": "response_time"}},
                    {
                        "bool": {
                            "filter": [
                                {"exists": {"field": "duration_ms"}},
                                {
                                    "bool": {
                                        "should": [
                                            {"term": {"is_execution_metric.keyword": "true"}},
                                            {"term": {"is_execution_metric": "true"}},
                                            {"term": {"perf_action.keyword": "End"}},
                                            {"term": {"perf_action": "End"}},
                                        ],
                                        "minimum_should_match": 1,
                                    }
                                },
                            ]
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
    ]

    # 2. Filter ambang batas minimal durasi jika ditentukan
    if min_response_time is not None:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"range": {"response_time": {"gte": min_response_time}}},
                        {"range": {"duration_ms": {"gte": min_response_time}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    query = {"bool": {"filter": filters}}

    # 3. Pengurutan dual-mode:
    # Memprioritaskan field yang tersedia tanpa error jika salah satu tidak ada
    result = es.search(
        index=index,
        from_=offset,
        size=limit,
        track_total_hits=True,
        query=query,
        sort=[
            {
                "duration_ms": {
                    "order": "desc",
                    "unmapped_type": "long",
                    "missing": "_last",
                }
            },
            {
                "response_time": {
                    "order": "desc",
                    "unmapped_type": "float",
                    "missing": "_last",
                }
            },
            {
                "@timestamp": {
                    "order": "desc",
                }
            },
        ],
        source=SOURCE_FIELDS,
    )

    hits = result["hits"]["hits"]
    total_matches = result["hits"]["total"]["value"]

    events = []
    for hit in hits:
        source = hit["_source"]

        # Normalisasi graceful fallback:
        # Jika duration_ms ada tapi response_time belum ada, isi response_time
        # agar konsumen lama tidak null.
        dur = source.get("duration_ms")
        resp = source.get("response_time")
        effective_duration = dur if dur is not None else resp

        if resp is None and dur is not None:
            source["response_time"] = dur

        # Jika request_path kosong tapi service_name ada, isi identifier
        service = source.get("service_name")
        step = source.get("step_name")
        if not source.get("request_path") and service:
            source["request_path"] = f"/{service}->{step}" if step else f"/{service}"

        source["effective_duration_ms"] = effective_duration
        events.append(source)

    return {
        "index": index,
        "time_range": {
            "start": time_range.start.isoformat(),
            "end": time_range.end.isoformat(),
        },
        "filters": {
            "min_response_time": min_response_time,
        },
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total_matches": total_matches,
            "count_returned": len(events),
            "has_more": offset + len(events) < total_matches,
            "next_offset": (
                offset + len(events) if offset + len(events) < total_matches else None
            ),
        },
        "slow_requests": events,
    }
