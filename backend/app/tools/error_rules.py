# Klasifikasi sementara berdasarkan kesepakatan
# monitoring. Perlu validasi lanjutan dari mentor.

TECHNICAL_4XX = frozenset({
    400, 404, 405, 408, 416, 429
})

BUSINESS_4XX = frozenset({
    401, 403, 422
})


def classify_http_status(status_code: int) -> str:
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        return "unknown"

    if status_code in TECHNICAL_4XX:
        return "technical_4xx"

    if status_code in BUSINESS_4XX:
        return "business_4xx"

    if 500 <= status_code <= 599:
        return "server_5xx"

    if 400 <= status_code <= 499:
        return "unclassified_4xx"

    if 100 <= status_code <= 399:
        return "non_error"

    return "unknown"
