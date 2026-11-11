from app.es_client import get_es_client
from app.models import TimeRange
from app.tools.validators import validate_index_pattern
from app.tools.error_rules import (
    TECHNICAL_4XX,
    BUSINESS_4XX,
)


def get_log_summary(
    index: str,
    time_range: TimeRange,
) -> dict:

    # 1. Validasi index pattern
    index = validate_index_pattern(index)

    # 2. Siapkan koneksi Elasticsearch
    es = get_es_client()

    # 3. Filter rentang waktu
    query = {
        "bool": {
            "filter": [
                {
                    "range": {
                        "@timestamp": {
                            "gte": time_range.start.isoformat(),
                            "lte": time_range.end.isoformat(),
                        }
                    }
                }
            ]
        }
    }

    # 4. Jalankan satu query agregasi Dual-Mode (HTTP + Microservice Tracing)
    result = es.search(
        index=index,
        size=0,
        track_total_hits=True,
        query=query,
        aggs={
            # --- HTTP Access Log Aggregations ---
            "status_distribution": {
                "terms": {
                    "field": "status_code",
                    "size": 20,
                }
            },
            "status_2xx": {
                "filter": {
                    "range": {
                        "status_code": {
                            "gte": 200,
                            "lt": 300,
                        }
                    }
                }
            },
            "status_3xx": {
                "filter": {
                    "range": {
                        "status_code": {
                            "gte": 300,
                            "lt": 400,
                        }
                    }
                }
            },
            "status_4xx": {
                "filter": {
                    "range": {
                        "status_code": {
                            "gte": 400,
                            "lt": 500,
                        }
                    }
                }
            },
            "status_5xx": {
                "filter": {
                    "range": {
                        "status_code": {
                            "gte": 500,
                            "lt": 600,
                        }
                    }
                }
            },
            "technical_4xx": {
                "filter": {
                    "terms": {
                        "status_code": sorted(TECHNICAL_4XX)
                    }
                }
            },
            "business_4xx": {
                "filter": {
                    "terms": {
                        "status_code": sorted(BUSINESS_4XX)
                    }
                }
            },

            # --- Microservice APM / Tracing Log Aggregations ---
            "log_level_distribution": {
                "terms": {
                    "field": "log_level.keyword",
                    "size": 10,
                }
            },
            "level_error": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"log_level.keyword": "ERROR"}},
                            {"term": {"log_level": "ERROR"}},
                            {"term": {"log_level": "error"}},
                        ]
                    }
                }
            },
            "level_warn": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"log_level.keyword": "WARN"}},
                            {"term": {"log_level": "WARN"}},
                            {"term": {"log_level": "warn"}},
                        ]
                    }
                }
            },
            "level_info": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"log_level.keyword": "INFO"}},
                            {"term": {"log_level": "INFO"}},
                            {"term": {"log_level": "info"}},
                        ]
                    }
                }
            },
            "level_debug": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"log_level.keyword": "DEBUG"}},
                            {"term": {"log_level": "DEBUG"}},
                            {"term": {"log_level": "debug"}},
                        ]
                    }
                }
            },
            "execution_metrics": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"is_execution_metric.keyword": "true"}},
                            {"term": {"is_execution_metric": "true"}},
                        ]
                    }
                }
            },
        },
    )

    total_events = result["hits"]["total"]["value"]

    # 5. Ekstraksi Metrik HTTP
    count_2xx = result["aggregations"]["status_2xx"]["doc_count"]
    count_3xx = result["aggregations"]["status_3xx"]["doc_count"]
    count_4xx = result["aggregations"]["status_4xx"]["doc_count"]
    count_5xx = result["aggregations"]["status_5xx"]["doc_count"]
    total_http_events = count_2xx + count_3xx + count_4xx + count_5xx

    count_technical = result["aggregations"]["technical_4xx"]["doc_count"]
    count_business = result["aggregations"]["business_4xx"]["doc_count"]
    count_unclassified = max(0, count_4xx - count_technical - count_business)
    http_errors = count_4xx + count_5xx

    status_distribution = {
        str(bucket["key"]): bucket["doc_count"]
        for bucket in result["aggregations"]["status_distribution"]["buckets"]
    }

    # 6. Ekstraksi Metrik Microservice Tracing
    count_error = result["aggregations"]["level_error"]["doc_count"]
    count_warn = result["aggregations"]["level_warn"]["doc_count"]
    count_info = result["aggregations"]["level_info"]["doc_count"]
    count_debug = result["aggregations"]["level_debug"]["doc_count"]
    total_log_levels = count_error + count_warn + count_info + count_debug

    log_level_distribution = {
        str(bucket["key"]): bucket["doc_count"]
        for bucket in result["aggregations"]["log_level_distribution"]["buckets"]
    }

    # Sinkronisasi log_level_distribution dengan filter hits jika terms belum muncul
    if count_error > 0 and "ERROR" not in log_level_distribution:
        log_level_distribution["ERROR"] = count_error
    if count_warn > 0 and "WARN" not in log_level_distribution:
        log_level_distribution["WARN"] = count_warn
    if count_info > 0 and "INFO" not in log_level_distribution:
        log_level_distribution["INFO"] = count_info
    if count_debug > 0 and "DEBUG" not in log_level_distribution:
        log_level_distribution["DEBUG"] = count_debug

    count_execution_metrics = result["aggregations"]["execution_metrics"]["doc_count"]

    # 7. Deteksi Otomatis Skema (Schema Detection)
    if total_log_levels > 0 and total_http_events == 0:
        schema_detected = "microservice_tracing"
        total_errors = count_error
    elif total_http_events > 0 and total_log_levels == 0:
        schema_detected = "http_access"
        total_errors = http_errors
    elif total_http_events > 0 and total_log_levels > 0:
        schema_detected = "hybrid"
        total_errors = http_errors + count_error
    else:
        schema_detected = "unknown"
        total_errors = http_errors + count_error

    def calculate_rate(count: int) -> float:
        if total_events == 0:
            return 0.0
        return round((count / total_events) * 100, 2)

    # 8. Output Respons Terintegrasi (Backward-Compatible)
    return {
        "index": index,
        "schema_detected": schema_detected,
        "time_range": {
            "start": time_range.start.isoformat(),
            "end": time_range.end.isoformat(),
        },
        "total_events": total_events,

        # HTTP status classes (tetap ada agar kode lama tidak breaking)
        "status_classes": {
            "2xx": count_2xx,
            "3xx": count_3xx,
            "4xx": count_4xx,
            "5xx": count_5xx,
        },
        "status_distribution": status_distribution,

        # Microservice APM / Tracing metrics
        "log_levels": {
            "DEBUG": count_debug,
            "INFO": count_info,
            "WARN": count_warn,
            "ERROR": count_error,
        },
        "log_level_distribution": log_level_distribution,
        "execution_metrics_count": count_execution_metrics,

        # Universal Errors
        "errors": {
            "total_errors": total_errors,
            # HTTP Error Counts
            "client_errors_4xx": count_4xx,
            "server_errors_5xx": count_5xx,
            # Tracing Error Counts
            "error_logs": count_error,
            "warn_logs": count_warn,
            # Rates
            "error_rate_percent": calculate_rate(total_errors),
            "client_error_rate_percent": calculate_rate(count_4xx),
            "server_error_rate_percent": calculate_rate(count_5xx),
            "error_log_rate_percent": calculate_rate(count_error),
        },

        # Detailed Error Categories
        "error_categories": {
            "technical_4xx": {
                "count": count_technical,
                "rate_percent": calculate_rate(count_technical),
            },
            "business_4xx": {
                "count": count_business,
                "rate_percent": calculate_rate(count_business),
            },
            "unclassified_4xx": {
                "count": count_unclassified,
                "rate_percent": calculate_rate(count_unclassified),
            },
            "server_5xx": {
                "count": count_5xx,
                "rate_percent": calculate_rate(count_5xx),
            },
            "error_logs": {
                "count": count_error,
                "rate_percent": calculate_rate(count_error),
            },
        },
    }
