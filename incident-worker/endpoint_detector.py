from elasticsearch import Elasticsearch


def poll_repeated_error_endpoints(
    es: Elasticsearch,
    index: str,
    start: str,
    end: str,
    max_paths: int = 100,
    exclude_416: bool = True,
) -> dict:
    filters = [
        {
            "range": {
                "@timestamp": {
                    "gte": start,
                    "lt": end,
                }
            }
        },
        {
            "range": {
                "status_code": {
                    "gte": 400,
                }
            }
        },
    ]

    must_not = []
    if exclude_416:
        # HTTP 416 dikecualikan hanya untuk
        # repeated endpoint detection.
        must_not.append(
            {
                "term": {
                    "status_code": 416
                }
            }
        )

    result = es.search(
        index=index,
        size=0,
        track_total_hits=True,
        query={
            "bool": {
                "filter": filters,
                "must_not": must_not,
            }
        },
        aggs={
            "error_paths": {
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
            }
        },
    )

    aggregation = result["aggregations"]["error_paths"]
    paths = []
    for bucket in aggregation["buckets"]:
        status_counts = {
            str(status["key"]): status["doc_count"]
            for status in bucket[
                "status_codes"
            ]["buckets"]
        }
        paths.append({
            "path": bucket["key"],
            "error_count": bucket["doc_count"],
            "status_counts": status_counts,
        })
    total_matching_errors = (
        result["hits"]["total"]["value"]
    )
    other_error_events = aggregation.get(
        "sum_other_doc_count", 0
    )
    represented_errors = (
        sum(item["error_count"] for item in paths)
        + other_error_events
    )
    missing_path_errors = max(
        0,
        total_matching_errors - represented_errors
    )
    # Terms aggregation bisa terbatas bila
    # jumlah endpoint sangat banyak.
    coverage_partial = (
        other_error_events > 0
        or missing_path_errors > 0
        or aggregation.get(
            "doc_count_error_upper_bound", 0
        ) > 0
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
