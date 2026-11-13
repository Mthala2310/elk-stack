OPENROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_index_info",
            "description": (
                "Get matching Elasticsearch indices and document count "
                "for an allowed index pattern."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Elasticsearch index or allowed index pattern, "
                            "for example app-logs-*."
                        ),
                    }
                },
                "required": ["index"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_latest_event",
            "description": (
                "Get the most recent log event from an allowed index "
                "(supports both HTTP access logs and Microservice tracing logs). "
                "Useful for checking data freshness."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Elasticsearch index or allowed index pattern."
                        ),
                    }
                },
                "required": ["index"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": (
                "Search detailed log events within an explicit time range. "
                "Supports HTTP filters (status_code, path), Microservice tracing filters "
                "(trace_id, service_name, step_name, log_level), and multi-field keyword search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": "Allowed Elasticsearch index pattern.",
                    },
                    "start": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "Start of the search time range in ISO 8601 "
                            "format including timezone."
                        ),
                    },
                    "end": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "End of the search time range in ISO 8601 "
                            "format including timezone."
                        ),
                    },
                    "status_code": {
                        "type": ["integer", "null"],
                        "description": (
                            "Optional exact HTTP status code (for HTTP logs), "
                            "for example 500."
                        ),
                    },
                    "path": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional HTTP request path filter (for HTTP logs), "
                            "for example /api/payments."
                        ),
                    },
                    "trace_id": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional exact distributed trace ID (for Microservice logs), "
                            "including negative sign if present, e.g. '-764967383'."
                        ),
                    },
                    "service_name": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional microservice name filter (for Microservice logs), "
                            "for example 'beneficiaryValidationNotification'."
                        ),
                    },
                    "step_name": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional execution step filter (for Microservice logs), "
                            "for example 'email' or 'prepare'."
                        ),
                    },
                    "log_level": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional severity level filter (for Microservice logs). "
                            "Allowed values: DEBUG, INFO, WARN, ERROR."
                        ),
                    },
                    "keyword": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional keyword to search across message, log_payload, "
                            "variable_name, variable_value, caller_class, caller_method, "
                            "service_name, step_name, and request_path."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Maximum number of matching events "
                            "returned in this response."
                        ),
                        "default": 20,
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Pagination offset.",
                        "default": 0,
                    },
                },
                "required": ["index", "start", "end"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "trace_lookup",
            "description": (
                "Reconstruct the complete chronological end-to-end execution timeline "
                "of a single microservice transaction by trace_id. Returns service metadata, "
                "status (SUCCESS/FAILED/IN_PROGRESS), end_to_end_duration_ms, "
                "total_step_duration_ms, executed steps with End durations, "
                "business input variables, and ERROR logs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Allowed Elasticsearch index or index pattern, "
                            "for example app-logs-* or app-logs-2026.10.14."
                        ),
                    },
                    "trace_id": {
                        "type": "string",
                        "description": (
                            "Exact distributed trace ID of the transaction, "
                            "including minus sign if negative (e.g. '518850885' or '-764967383')."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": (
                            "Maximum number of spans/events to fetch for this trace."
                        ),
                        "default": 100,
                    },
                },
                "required": ["index", "trace_id"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_log_summary",
            "description": (
                "Get an aggregated dual-mode summary of logs for a time range. "
                "Auto-detects schema_detected ('http_access', 'microservice_tracing', or 'hybrid'), "
                "returning total events, HTTP status distribution (2xx-5xx), "
                "Microservice log_levels (DEBUG/INFO/WARN/ERROR), execution_metrics_count, and error rates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": "Allowed Elasticsearch index pattern.",
                    },
                    "start": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "Start of the analysis period "
                            "in ISO 8601 format with timezone."
                        ),
                    },
                    "end": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "End of the analysis period "
                            "in ISO 8601 format with timezone."
                        ),
                    },
                },
                "required": ["index", "start", "end"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_top_error_paths",
            "description": (
                "Find components with the highest number of errors in a given time range. "
                "For HTTP logs, ranks request_path with 4xx/5xx errors; for Microservice logs, "
                "ranks service_name (with step breakdown) or fallback caller_class with log_level ERROR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": "Allowed Elasticsearch index pattern.",
                    },
                    "start": {
                        "type": "string",
                        "format": "date-time",
                    },
                    "end": {
                        "type": "string",
                        "format": "date-time",
                    },
                    "error_class": {
                        "type": "string",
                        "enum": ["all", "4xx", "5xx"],
                        "description": (
                            "Error class to analyze ('all' and '5xx' also include Microservice ERROR logs)."
                        ),
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Number of top error paths or services to return.",
                        "default": 10,
                    },
                },
                "required": ["index", "start", "end"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_slow_requests",
            "description": (
                "Find the slowest HTTP requests (by response_time) or slowest Microservice step executions "
                "(by duration_ms on completed 'End' spans, excluding 'Start' timeout countdowns). "
                "Optionally filter by minimum latency in ms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": "Allowed Elasticsearch index pattern.",
                    },
                    "start": {
                        "type": "string",
                        "format": "date-time",
                    },
                    "end": {
                        "type": "string",
                        "format": "date-time",
                    },
                    "min_response_time": {
                        "type": ["number", "null"],
                        "minimum": 0,
                        "description": (
                            "Optional minimum latency threshold in ms "
                            "(applies to both HTTP response_time and Microservice duration_ms)."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 10,
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                    },
                },
                "required": ["index", "start", "end"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_error_peak_hours",
            "description": (
                "Find peak error hours or multi-hour consecutive time windows "
                "with the highest number of errors (supports both HTTP 4xx/5xx and Microservice ERROR logs)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Allowed Elasticsearch index or index pattern."
                        ),
                    },
                    "start": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "Analysis start in ISO 8601 including timezone."
                        ),
                    },
                    "end": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "Analysis end in ISO 8601 including timezone."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "all_errors",
                            "error_logs",
                            "technical_4xx",
                            "business_4xx",
                            "server_5xx",
                            "unclassified_4xx",
                        ],
                        "description": (
                            "Operational error category. Use 'all_errors' for general dual-mode errors "
                            "or 'error_logs' specifically for Microservice ERROR level logs."
                        ),
                    },
                    "status_code": {
                        "type": ["integer", "null"],
                        "minimum": 400,
                        "maximum": 599,
                        "description": (
                            "Optional exact HTTP error status (HTTP logs only). "
                            "When set, category must be all_errors."
                        ),
                    },
                    "path": {
                        "type": ["string", "null"],
                        "description": "Optional exact HTTP request path.",
                    },
                    "service_name": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional microservice name filter (for Microservice logs)."
                        ),
                    },
                    "window_hours": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": (
                            "Duration of the peak time window in consecutive hours."
                        ),
                    },
                },
                "required": ["index", "start", "end"],
                "additionalProperties": False,
            },
        },
    },
]
