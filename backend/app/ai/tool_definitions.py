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
                "Get the most recent log event from an allowed index. "
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
                "Search log events within an explicit time range. "
                "Can filter by HTTP status code, request path, "
                "keyword, limit, and pagination offset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Allowed Elasticsearch index pattern."
                        ),
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
                            "Optional exact HTTP status code, "
                            "for example 500."
                        ),
                    },

                    "path": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional request path filter, "
                            "for example /api/payments."
                        ),
                    },

                    "keyword": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional keyword to search in supported "
                            "log fields."
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
                        "description": (
                            "Pagination offset."
                        ),
                        "default": 0,
                    },
                },

                "required": [
                    "index",
                    "start",
                    "end"
                ],

                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_log_summary",
            "description": (
                "Get an aggregated summary of logs for a time range, "
                "including total events, HTTP status distribution, "
                "4xx/5xx counts, and error rates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Allowed Elasticsearch index pattern."
                        ),
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

                "required": [
                    "index",
                    "start",
                    "end"
                ],

                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_top_error_paths",
            "description": (
                "Find request paths with the highest number of "
                "HTTP errors in a given time range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Allowed Elasticsearch index pattern."
                        ),
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
                        "enum": [
                            "all",
                            "4xx",
                            "5xx"
                        ],
                        "description": (
                            "Error class to analyze."
                        ),
                        "default": "all",
                    },

                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Number of top error paths to return."
                        ),
                        "default": 10,
                    },
                },

                "required": [
                    "index",
                    "start",
                    "end"
                ],

                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_slow_requests",
            "description": (
                "Find the slowest requests in a given time range, "
                "optionally filtering by a minimum response time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Allowed Elasticsearch index pattern."
                        ),
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
                            "Optional minimum response_time threshold."
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

                "required": [
                    "index",
                    "start",
                    "end"
                ],

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
                "with the highest number of errors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": (
                            "Allowed Elasticsearch index "
                            "or index pattern."
                        ),
                    },
                    "start": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "Analysis start in ISO 8601 "
                            "including timezone."
                        ),
                    },
                    "end": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "Analysis end in ISO 8601 "
                            "including timezone."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "all_errors",
                            "technical_4xx",
                            "business_4xx",
                            "server_5xx",
                            "unclassified_4xx",
                        ],
                        "description": (
                            "Operational error category. "
                            "Defaults to all_errors."
                        ),
                    },
                    "status_code": {
                        "type": ["integer", "null"],
                        "minimum": 400,
                        "maximum": 599,
                        "description": (
                            "Optional exact HTTP error status. "
                            "When set, category must be all_errors."
                        ),
                    },
                    "path": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional exact request path."
                        ),
                    },
                    "window_hours": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": (
                            "Duration of the peak time window "
                            "in consecutive hours."
                        ),
                    },
                },
                "required": [
                    "index",
                    "start",
                    "end",
                ],
                "additionalProperties": False,
            },
        },
    },
]