from typing import Any
from app.es_client import get_es_client
from app.models import TimeRange
from app.tools.validators import (
    validate_index_pattern,
    validate_limit,
)

SOURCE_FIELDS = [
    "@timestamp",
    # HTTP Access Log fields
    "ip_addr",
    "http_method",
    "request_path",
    "http_version",
    "status_code",
    "request_size",
    "referrer",
    "user_agent",
    "response_time",
    # Microservice Tracing & APM fields
    "log_level",
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
    "variable_name",
    "variable_value",
    "log_payload",
    "message",
]


def search_logs(
    index: str,
    time_range: TimeRange,
    status_code: int | None = None,
    path: str | None = None,
    keyword: str | None = None,
    trace_id: str | None = None,
    service_name: str | None = None,
    step_name: str | None = None,
    log_level: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    index = validate_index_pattern(index)
    limit = validate_limit(limit)
    if offset < 0:
        raise ValueError("offset tidak boleh negatif")

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

    must: list[dict[str, Any]] = []

    # 1. Filter HTTP lama
    if status_code is not None:
        filters.append({"term": {"status_code": status_code}})

    if path is not None:
        filters.append({"match": {"request_path": path}})

    # 2. Filter Microservice baru
    if trace_id is not None:
        clean_trace_id = str(trace_id).strip()
        filters.append({
            "bool": {
                "should": [
                    {"term": {"trace_id.keyword": clean_trace_id}},
                    {"term": {"trace_id": clean_trace_id}},
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

    if step_name is not None:
        filters.append({
            "bool": {
                "should": [
                    {"term": {"step_name.keyword": step_name}},
                    {"match": {"step_name": step_name}},
                ],
                "minimum_should_match": 1,
            }
        })

    if log_level is not None:
        lvl = log_level.strip().upper()
        filters.append({
            "bool": {
                "should": [
                    {"term": {"log_level.keyword": lvl}},
                    {"term": {"log_level": lvl}},
                    {"term": {"log_level": lvl.lower()}},
                ],
                "minimum_should_match": 1,
            }
        })

    # 3. Keyword search lintas field (log lama & baru)
    if keyword is not None:
        must.append({
            "multi_match": {
                "query": keyword,
                "fields": [
                    "message",
                    "log_payload",
                    "variable_name",
                    "variable_value",
                    "caller_class",
                    "caller_method",
                    "service_name",
                    "step_name",
                    "request_path",
                ],
                "lenient": True,
            }
        })

    query: dict[str, Any] = {"bool": {"filter": filters}}
    if must:
        query["bool"]["must"] = must

    result = es.search(
        index=index,
        from_=offset,
        size=limit,
        track_total_hits=True,
        query=query,
        sort=[
            {
                "@timestamp": {
                    "order": "desc",
                }
            }
        ],
        source=SOURCE_FIELDS,
    )
    hits = result["hits"]["hits"]

    total_matches = (
        result["hits"]["total"]["value"]
        if isinstance(result["hits"]["total"], dict)
        else result["hits"]["total"]
    )

    events = [hit["_source"] for hit in hits]

    return {
        "index": index,
        "time_range": {
            "start": time_range.start.isoformat(),
            "end": time_range.end.isoformat(),
        },
        "filters": {
            "status_code": status_code,
            "path": path,
            "keyword": keyword,
            "trace_id": trace_id,
            "service_name": service_name,
            "step_name": step_name,
            "log_level": log_level,
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
        "events": events,
    }
