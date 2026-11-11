from typing import Any
from app.es_client import get_es_client
from app.models import TimeRange

from app.tools.validators import (
    validate_index_pattern,
    validate_limit,
)


def get_top_error_paths(
    index: str,
    time_range: TimeRange,
    error_class: str = "all",
    limit: int = 10,
) -> dict:

    index = validate_index_pattern(index)
    limit = validate_limit(limit)

    error_class = error_class.lower()

    if error_class not in {"all", "4xx", "5xx"}:
        raise ValueError("error_class hanya boleh: all, 4xx, atau 5xx")

    es = get_es_client()

    # 1. Bangun filter error dual-mode:
    # Mendukung HTTP status_code (4xx/5xx) dan Microservice log_level (ERROR)
    error_conditions: list[dict[str, Any]] = []

    if error_class == "4xx":
        error_conditions.append(
            {"range": {"status_code": {"gte": 400, "lt": 500}}}
        )
    elif error_class == "5xx":
        error_conditions.append(
            {"range": {"status_code": {"gte": 500, "lt": 600}}}
        )
        error_conditions.extend([
            {"term": {"log_level.keyword": "ERROR"}},
            {"term": {"log_level": "ERROR"}},
            {"term": {"log_level": "error"}},
        ])
    else:  # "all"
        error_conditions.append(
            {"range": {"status_code": {"gte": 400, "lt": 600}}}
        )
        error_conditions.extend([
            {"term": {"log_level.keyword": "ERROR"}},
            {"term": {"log_level": "ERROR"}},
            {"term": {"log_level": "error"}},
        ])

    filters: list[dict[str, Any]] = [
        {
            "range": {
                "@timestamp": {
                    "gte": time_range.start.isoformat(),
                    "lte": time_range.end.isoformat(),
                }
            }
        },
        {
            "bool": {
                "should": error_conditions,
                "minimum_should_match": 1,
            }
        },
    ]

    # 2. Agregasi multi-sumber:
    # - top_http_paths: untuk log HTTP lama (request_path)
    # - top_microservices: untuk log Microservice Pola A/B/C (punya service_name)
    # - top_callers_no_service: untuk log Microservice Pola D fallback (hanya punya caller_class, tanpa service_name)
    result = es.search(
        index=index,
        size=0,
        track_total_hits=True,
        query={"bool": {"filter": filters}},
        aggs={
            "top_http_paths": {
                "terms": {
                    "field": "request_path.keyword",
                    "size": limit,
                    "order": {"_count": "desc"},
                }
            },
            "top_microservices": {  
                "terms": {
                    "field": "service_name.keyword",
                    "size": limit,
                    "order": {"_count": "desc"},
                },
                "aggs": {
                    "steps": {
                        "terms": {
                            "field": "step_name.keyword",
                            "size": 5,
                        }
                    }
                },
            },
            "top_callers_no_service": {
                "filter": {
                    "bool": {
                        "must_not": [
                            {"exists": {"field": "service_name"}},
                            {"exists": {"field": "request_path"}},
                        ]
                    }
                },
                "aggs": {
                    "callers": {
                        "terms": {
                            "field": "caller_class.keyword",
                            "size": limit,
                            "order": {"_count": "desc"},
                        },
                        "aggs": {
                            "methods": {
                                "terms": {
                                    "field": "caller_method.keyword",
                                    "size": 5,
                                }
                            }
                        },
                    }
                },
            },
        },
    )

    total_error_events = result["hits"]["total"]["value"]

    http_buckets = (
        result["aggregations"].get("top_http_paths", {}).get("buckets", [])
    )
    service_buckets = (
        result["aggregations"].get("top_microservices", {}).get("buckets", [])
    )
    caller_buckets = (
        result["aggregations"]
        .get("top_callers_no_service", {})
        .get("callers", {})
        .get("buckets", [])
    )

    def calc_pct(count: int) -> float:
        if total_error_events <= 0:
            return 0.0
        return round((count / total_error_events) * 100, 2)

    combined_items: list[dict[str, Any]] = []

    # 3A. Masukkan error dari HTTP Endpoint
    for b in http_buckets:
        count = b["doc_count"]
        combined_items.append({
            "request_path": b["key"],
            "target_type": "http_endpoint",
            "error_count": count,
            "percentage_of_error_events": calc_pct(count),
        })

    # 3B. Masukkan error dari Microservice (Pola A/B/C) beserta detail step-nya
    for b in service_buckets:
        count = b["doc_count"]
        step_breakdown = {
            sb["key"]: sb["doc_count"]
            for sb in b.get("steps", {}).get("buckets", [])
        }
        item: dict[str, Any] = {
            "request_path": f"/service/{b['key']}",
            "service_name": b["key"],
            "target_type": "microservice",
            "error_count": count,
            "percentage_of_error_events": calc_pct(count),
        }
        if step_breakdown:
            item["steps"] = step_breakdown
        combined_items.append(item)

    # 3C. Masukkan error dari Pola D Fallback (log umum tanpa service_name)
    for b in caller_buckets:
        count = b["doc_count"]
        method_breakdown = {
            mb["key"]: mb["doc_count"]
            for mb in b.get("methods", {}).get("buckets", [])
        }
        item_caller: dict[str, Any] = {
            "request_path": f"/class/{b['key']}",
            "caller_class": b["key"],
            "target_type": "caller_class",
            "error_count": count,
            "percentage_of_error_events": calc_pct(count),
        }
        if method_breakdown:
            item_caller["methods"] = method_breakdown
        combined_items.append(item_caller)

    # Urutkan keseluruhan berdasarkan jumlah error terbanyak
    combined_items.sort(key=lambda x: -x["error_count"])
    top_paths = combined_items[:limit]

    return {
        "index": index,
        "time_range": {
            "start": time_range.start.isoformat(),
            "end": time_range.end.isoformat(),
        },
        "error_class": error_class,
        "total_error_events": total_error_events,
        "limit": limit,
        "count_returned": len(top_paths),
        "top_error_paths": top_paths,
    }
