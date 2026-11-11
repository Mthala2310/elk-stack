from math import isfinite


def poll_latency(
    es,
    index: str,
    start: str,
    end: str,
    threshold_ms: int,
) -> dict:
    if (
        isinstance(threshold_ms, bool)
        or not isinstance(threshold_ms, int)
        or threshold_ms < 1
    ):
        raise ValueError(
            "threshold_ms harus integer positif."
        )

    # 1. Gunakan window yang sama
    # dengan Incident Worker.
    query = {
        "range": {
            "@timestamp": {
                "gte": start,
                "lt": end,
            }
        }
    }

    # 2. Minta Elasticsearch menghitung
    # statistik latency tanpa mengambil raw log.
    result = es.search(
        index=index,
        size=0,
        query=query,
        aggs={
            "valid_latency": {
                "filter": {
                    "range": {
                        "response_time": {
                            "gte": 0
                        }
                    }
                },
                "aggs": {
                    "p95": {
                        "percentiles": {
                            "field": "response_time",
                            "percents": [95.0],
                        }
                    },
                    "slow_requests": {
                        "filter": {
                            "range": {
                                "response_time": {
                                    "gte": threshold_ms
                                }
                            }
                        }
                    },
                },
            }
        },
    )

    valid = result["aggregations"]["valid_latency"]
    samples = valid["doc_count"]
    p95_raw = valid["p95"]["values"].get("95.0")
    slow_count = valid["slow_requests"]["doc_count"]

    if p95_raw is None or not isfinite(p95_raw):
        p95_ms = None
    else:
        p95_ms = round(float(p95_raw), 2)

    slow_rate = (
        round((slow_count / samples) * 100, 2)
        if samples > 0
        else None
    )

    return {
        "unit": "ms",
        "threshold_ms": threshold_ms,
        "sample_count": samples,
        "p95_ms": p95_ms,
        "slow_request_count": slow_count,
        "slow_request_rate_percent": slow_rate,
    }
