from typing import Any
from elasticsearch import Elasticsearch


def poll_repeated_error_endpoints(
    es: Elasticsearch,
    index: str,
    start: str,
    end: str,
    max_paths: int = 100,
    exclude_416: bool = True,
) -> dict:
    # 1. Filter error HTTP (status_code >= 400, opsional exclude 416)
    http_error_filter: dict[str, Any] = {
        "bool": {
            "filter": [
                {"range": {"status_code": {"gte": 400}}}
            ]
        }
    }
    if exclude_416:
        http_error_filter["bool"]["must_not"] = [
            {"term": {"status_code": 416}}
        ]

    # 2. Filter error Microservice (log_level == ERROR)
    apm_error_filter: dict[str, Any] = {
        "bool": {
            "should": [
                {"term": {"log_level.keyword": "ERROR"}},
                {"term": {"log_level": "ERROR"}},
                {"term": {"log_level": "error"}},
            ],
            "minimum_should_match": 1,
        }
    }

    filters: list[dict[str, Any]] = [
        {
            "range": {
                "@timestamp": {
                    "gte": start,
                    "lt": end,
                }
            }
        },
        {
            "bool": {
                "should": [
                    http_error_filter,
                    apm_error_filter,
                ],
                "minimum_should_match": 1,
            }
        },
    ]

    # 3. Agregasi 3 jalur tanpa duplikasi:
    # - error_http_paths: untuk HTTP request_path
    # - error_microservices: untuk Microservice Pola A/B/C (punya service_name)
    # - error_callers_no_service: untuk Microservice Pola D fallback (hanya caller_class)
    result = es.search(
        index=index,
        size=0,
        track_total_hits=True,
        query={"bool": {"filter": filters}},
        aggs={
            "error_http_paths": {
                "terms": {
                    "field": "request_path.keyword",
                    "size": max_paths,
                },
                "aggs": {
                    "status_codes": {
                        "terms": {
                            "field": "status_code",
                            "size": 100,
                        }
                    }
                },
            },
            "error_microservices": {
                "terms": {
                    "field": "service_name.keyword",
                    "size": max_paths,
                },
                "aggs": {
                    "steps": {
                        "terms": {
                            "field": "step_name.keyword",
                            "size": 20,
                        }
                    }
                },
            },
            "error_callers_no_service": {
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
                            "size": max_paths,
                        },
                        "aggs": {
                            "methods": {
                                "terms": {
                                    "field": "caller_method.keyword",
                                    "size": 20,
                                }
                            }
                        },
                    }
                },
            },
        },
    )

    aggs = result["aggregations"]
    http_agg = aggs.get("error_http_paths", {})
    service_agg = aggs.get("error_microservices", {})
    caller_agg = aggs.get("error_callers_no_service", {}).get("callers", {})

    paths: list[dict[str, Any]] = []

    # A. HTTP Endpoint Errors
    for bucket in http_agg.get("buckets", []):
        status_counts = {
            str(status["key"]): status["doc_count"]
            for status in bucket.get("status_codes", {}).get("buckets", [])
        }
        paths.append({
            "path": bucket["key"],
            "target_type": "http_endpoint",
            "error_count": bucket["doc_count"],
            "status_counts": status_counts,
        })

    # B. Microservice Service Errors (Pola A/B/C)
    for bucket in service_agg.get("buckets", []):
        step_counts = {
            f"step:{s['key']}": s["doc_count"]
            for s in bucket.get("steps", {}).get("buckets", [])
        }
        paths.append({
            "path": f"/service/{bucket['key']}",
            "target_type": "microservice",
            "error_count": bucket["doc_count"],
            "status_counts": step_counts or {"ERROR": bucket["doc_count"]},
        })

    # C. Microservice Caller Class Fallback Errors (Pola D)
    for bucket in caller_agg.get("buckets", []):
        method_counts = {
            f"method:{m['key']}": m["doc_count"]
            for m in bucket.get("methods", {}).get("buckets", [])
        }
        paths.append({
            "path": f"/class/{bucket['key']}",
            "target_type": "caller_class",
            "error_count": bucket["doc_count"],
            "status_counts": method_counts or {"ERROR": bucket["doc_count"]},
        })

    paths.sort(key=lambda item: -item["error_count"])

    total_matching_errors = result["hits"]["total"]["value"]
    other_error_events = (
        http_agg.get("sum_other_doc_count", 0)
        + service_agg.get("sum_other_doc_count", 0)
        + caller_agg.get("sum_other_doc_count", 0)
    )
    represented_errors = (
        sum(item["error_count"] for item in paths)
        + other_error_events
    )
    missing_path_errors = max(0, total_matching_errors - represented_errors)
    upper_bound_error = max(
        http_agg.get("doc_count_error_upper_bound", 0),
        service_agg.get("doc_count_error_upper_bound", 0),
        caller_agg.get("doc_count_error_upper_bound", 0),
    )

    coverage_partial = (
        other_error_events > 0
        or missing_path_errors > 0
        or upper_bound_error > 0
    )

    return {
        "index": index,
        "window_start": start,
        "window_end": end,
        "total_matching_errors": total_matching_errors,
        "exclude_416": exclude_416,
        "paths_checked": len(paths),
        "paths": paths,
        "other_error_events": other_error_events,
        "missing_path_errors": missing_path_errors,
        "coverage_partial": coverage_partial,
    }
