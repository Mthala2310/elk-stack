from math import isfinite
from typing import Any


def _safe_p95(raw_value: Any) -> float | None:
    if (
        raw_value is None
        or isinstance(raw_value, bool)
        or not isinstance(raw_value, (int, float))
        or not isfinite(raw_value)
    ):
        return None
    return float(raw_value)


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

    # 1. Gunakan window waktu yang sama dengan Incident Worker
    query = {
        "range": {
            "@timestamp": {
                "gte": start,
                "lt": end,
            }
        }
    }

    # 2. Hitung statistik latency Dual-Mode dalam 1 query:
    # - Jalur HTTP: field 'response_time'
    # - Jalur Microservice: field 'duration_ms' KHUSUS baris selesai ('End' / 'is_execution_metric: true')
    #   (Penting: baris 'Start [29998 ms]' adalah sisa timeout budget, BUKAN durasi proses!)
    result = es.search(
        index=index,
        size=0,
        query=query,
        aggs={
            "valid_http_latency": {
                "filter": {
                    "range": {
                        "response_time": {"gte": 0}
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
                                "response_time": {"gte": threshold_ms}
                            }
                        }
                    },
                },
            },
            "valid_apm_latency": {
                "filter": {
                    "bool": {
                        "filter": [
                            {"range": {"duration_ms": {"gte": 0}}},
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
                "aggs": {
                    "p95": {
                        "percentiles": {
                            "field": "duration_ms",
                            "percents": [95.0],
                        }
                    },
                    "slow_requests": {
                        "filter": {
                            "range": {
                                "duration_ms": {"gte": threshold_ms}
                            }
                        }
                    },
                },
            },
        },
    )

    aggs = result["aggregations"]

    valid_http = aggs["valid_http_latency"]
    http_samples = valid_http["doc_count"]
    http_p95 = _safe_p95(valid_http["p95"]["values"].get("95.0"))
    http_slow = valid_http["slow_requests"]["doc_count"]

    valid_apm = aggs["valid_apm_latency"]
    apm_samples = valid_apm["doc_count"]
    apm_p95 = _safe_p95(valid_apm["p95"]["values"].get("95.0"))
    apm_slow = valid_apm["slow_requests"]["doc_count"]

    # 3. Gabungkan sesuai skema yang terdeteksi
    if http_samples > 0 and apm_samples > 0:
        schema_detected = "hybrid"
        samples = http_samples + apm_samples
        slow_count = http_slow + apm_slow
        p95_candidates = [v for v in (http_p95, apm_p95) if v is not None]
        p95_ms = round(max(p95_candidates), 2) if p95_candidates else None
    elif apm_samples > 0:
        schema_detected = "microservice_tracing"
        samples = apm_samples
        slow_count = apm_slow
        p95_ms = round(apm_p95, 2) if apm_p95 is not None else None
    elif http_samples > 0:
        schema_detected = "http_access"
        samples = http_samples
        slow_count = http_slow
        p95_ms = round(http_p95, 2) if http_p95 is not None else None
    else:
        schema_detected = "no_data"
        samples = 0
        slow_count = 0
        p95_ms = None

    slow_rate = (
        round((slow_count / samples) * 100, 2)
        if samples > 0
        else None
    )

    return {
        "unit": "ms",
        "schema_detected": schema_detected,
        "threshold_ms": threshold_ms,
        "sample_count": samples,
        "http_sample_count": http_samples,
        "apm_sample_count": apm_samples,
        "p95_ms": p95_ms,
        "slow_request_count": slow_count,
        "slow_request_rate_percent": slow_rate,
    }
