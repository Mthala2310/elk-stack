from dataclasses import dataclass
from math import isfinite
import os


# ======================================
# 1. RULE CONFIGURATION
# ======================================


@dataclass(frozen=True)
class RuleConfig:
    min_total_requests: int = 100
    rate_5xx_threshold: float = 5.0
    min_5xx_errors: int = 10
    rate_4xx_threshold: float = 20.0
    min_4xx_errors: int = 30
    # Minimal error pada endpoint yang sama
    repeated_min_errors: int = 10
    latency_threshold_ms: int = 4000
    latency_min_samples: int = 100
    latency_min_slow_requests: int = 15

    def __post_init__(self):
        if self.min_total_requests < 1:
            raise ValueError("Minimal request harus >= 1.")

        for count in (
            self.min_5xx_errors,
            self.min_4xx_errors,
        ):
            if count < 1:
                raise ValueError("Minimal jumlah error harus >= 1.")

        if self.repeated_min_errors < 1:
            raise ValueError(
                "repeated_min_errors harus >= 1."
            )

        for rate in (
            self.rate_5xx_threshold,
            self.rate_4xx_threshold,
        ):
            if not 0 <= rate <= 100:
                raise ValueError("Threshold rate harus antara 0-100.")

        for name, value in (
            ("latency_threshold_ms", self.latency_threshold_ms),
            ("latency_min_samples", self.latency_min_samples),
            (
                "latency_min_slow_requests",
                self.latency_min_slow_requests,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise ValueError(
                    f"{name} harus integer positif."
                )

    @classmethod
    def from_env(cls):
        return cls(
            min_total_requests=int(
                os.getenv("INCIDENT_MIN_TOTAL_REQUESTS", "100")
            ),
            rate_5xx_threshold=float(
                os.getenv("INCIDENT_5XX_RATE_THRESHOLD_PERCENT", "5.0")
            ),
            min_5xx_errors=int(os.getenv("INCIDENT_5XX_MIN_ERRORS", "10")),
            rate_4xx_threshold=float(
                os.getenv("INCIDENT_4XX_RATE_THRESHOLD_PERCENT", "20.0")
            ),
            min_4xx_errors=int(os.getenv("INCIDENT_4XX_MIN_ERRORS", "30")),
            repeated_min_errors=int(
                os.getenv(
                    "INCIDENT_REPEATED_MIN_ERRORS",
                    "10"
                )
            ),
            latency_threshold_ms=int(
                os.getenv(
                    "INCIDENT_LATENCY_THRESHOLD_MS",
                    "3000"
                )
            ),
            latency_min_samples=int(
                os.getenv(
                    "INCIDENT_LATENCY_MIN_SAMPLES",
                    "100"
                )
            ),
            latency_min_slow_requests=int(
                os.getenv(
                    "INCIDENT_LATENCY_MIN_SLOW_REQUESTS",
                    "10"
                )
            ),
        )


# ======================================
# 2. RULE EVALUATION
# ======================================


def evaluate_rate_rule(
    rule_id: str,
    total_events: int,
    error_count: int,
    rate_threshold: float,
    min_errors: int,
    min_total_requests: int,
) -> dict:
    threshold_obj = {
        "rate_percent": rate_threshold,
        "min_error_count": min_errors,
    }

    if total_events == 0:
        return {
            "rule_id": rule_id,
            "status": "NO_DATA",
            "total_events": total_events,
            "error_count": error_count,
            "error_rate_percent": None,
            "threshold": threshold_obj,
            "threshold_rate_percent": rate_threshold,
            "min_errors": min_errors,
        }

    rate = round((error_count / total_events) * 100, 2)

    if total_events < min_total_requests:
        return {
            "rule_id": rule_id,
            "status": "LOW_TRAFFIC",
            "total_events": total_events,
            "error_count": error_count,
            "error_rate_percent": rate,
            "threshold": threshold_obj,
            "threshold_rate_percent": rate_threshold,
            "min_errors": min_errors,
        }

    if rate >= rate_threshold and error_count >= min_errors:
        status = "TRIGGERED"
    else:
        status = "NORMAL"

    return {
        "rule_id": rule_id,
        "status": status,
        "total_events": total_events,
        "error_count": error_count,
        "error_rate_percent": rate,
        "threshold": threshold_obj,
        "threshold_rate_percent": rate_threshold,
        "min_errors": min_errors,
    }


def evaluate_repeated_endpoints(
    endpoint_snapshot: dict,
    min_error_count: int,
    window_total_events: int,
) -> dict:
    triggered = []
    # Evaluasi setiap endpoint hasil agregasi
    for item in endpoint_snapshot["paths"]:
        error_count = item["error_count"]
        if error_count >= min_error_count:
            triggered.append({
                "incident_key": (
                    "REPEATED_ERROR_ENDPOINT:"
                    + item["path"]
                ),
                "path": item["path"],
                "error_count": error_count,
                "status_counts": item["status_counts"],
            })
    # Urutkan dari jumlah error terbesar
    triggered.sort(
        key=lambda item: -item["error_count"]
    )
    if window_total_events == 0:
        status = "NO_DATA"
    elif triggered:
        status = "TRIGGERED"
    elif endpoint_snapshot["coverage_partial"]:
        status = "INCOMPLETE"
    else:
        status = "NORMAL"
    return {
        "rule_id": "REPEATED_ERROR_ENDPOINT",
        "status": status,
        "threshold": {
            "min_errors_per_endpoint": min_error_count,
            "exclude_416": endpoint_snapshot[
                "exclude_416"
            ],
        },
        "total_matching_errors": endpoint_snapshot[
            "total_matching_errors"
        ],
        "paths_checked": endpoint_snapshot[
            "paths_checked"
        ],
        "coverage_partial": endpoint_snapshot[
            "coverage_partial"
        ],
        "triggered_endpoints": triggered,
    }


def evaluate_latency_rule(
    latency_snapshot: dict,
    config: RuleConfig,
) -> dict:
    # Pastikan satuan sesuai keputusan project
    if latency_snapshot["unit"] != "ms":
        raise ValueError(
            "Latency harus menggunakan satuan ms."
        )

    if (
        latency_snapshot["threshold_ms"]
        != config.latency_threshold_ms
    ):
        raise ValueError(
            "Threshold detector dan Rule Engine berbeda."
        )

    samples = latency_snapshot["sample_count"]
    slow_count = latency_snapshot["slow_request_count"]
    p95 = latency_snapshot["p95_ms"]

    # Validasi hasil agregasi
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        for value in (samples, slow_count)
    ):
        raise ValueError("Count latency harus integer.")

    if samples < 0 or not 0 <= slow_count <= samples:
        raise ValueError(
            "Jumlah sampel latency tidak valid."
        )

    if p95 is not None:
        if (
            isinstance(p95, bool)
            or not isinstance(p95, (int, float))
            or not isfinite(p95)
            or p95 < 0
        ):
            raise ValueError("P95 latency tidak valid.")

    # Tidak ada data latency.
    # Jangan otomatis menganggap NORMAL.
    if samples == 0:
        status = "NO_LATENCY_DATA"
    elif samples < config.latency_min_samples:
        status = "LOW_SAMPLE"
    elif p95 is None:
        status = "UNKNOWN"
    elif (
        p95 >= config.latency_threshold_ms
        and slow_count >= config.latency_min_slow_requests
    ):
        status = "TRIGGERED"
    else:
        status = "NORMAL"

    return {
        "rule_id": "HIGH_RESPONSE_TIME",
        "status": status,
        "sample_count": samples,
        "p95_ms": p95,
        "slow_request_count": slow_count,
        "slow_request_rate_percent": latency_snapshot.get(
            "slow_request_rate_percent"
        ),
        "threshold": config.latency_threshold_ms,
        "min_samples": config.latency_min_samples,
        "min_slow_requests": config.latency_min_slow_requests,
        "unit": "ms",
    }


def evaluate_rules(
    snapshot: dict,
    config: RuleConfig,
    endpoint_snapshot: dict | None = None,
    stale_rule: dict | None = None,
    latency_snapshot: dict | None = None,
) -> dict:
    total = snapshot.get("total_events", 0)
    count_4xx = snapshot.get("count_4xx", 0)
    count_5xx = snapshot.get("count_5xx", 0)

    rule_5xx = evaluate_rate_rule(
        rule_id="HIGH_5XX_ERROR_RATE",
        total_events=total,
        error_count=count_5xx,
        rate_threshold=config.rate_5xx_threshold,
        min_errors=config.min_5xx_errors,
        min_total_requests=config.min_total_requests,
    )

    rule_4xx = evaluate_rate_rule(
        rule_id="HIGH_4XX_ERROR_RATE",
        total_events=total,
        error_count=count_4xx,
        rate_threshold=config.rate_4xx_threshold,
        min_errors=config.min_4xx_errors,
        min_total_requests=config.min_total_requests,
    )

    rules = [rule_5xx, rule_4xx]

    # Tambahkan evaluasi repeated endpoint
    # tanpa mengubah rule 4xx dan 5xx.
    if endpoint_snapshot is not None:
        repeated_rule = evaluate_repeated_endpoints(
            endpoint_snapshot=endpoint_snapshot,
            min_error_count=config.repeated_min_errors,
            window_total_events=total,
        )
        rules.append(repeated_rule)

    # Masukkan rule Stale / No Log
    if stale_rule is not None:
        if stale_rule["rule_id"] != "STALE_NO_LOG":
            raise ValueError(
                "Rule stale tidak dikenal."
            )
        rules.append(stale_rule)

    # Tambahkan rule High Response Time
    if latency_snapshot is not None:
        latency_rule = evaluate_latency_rule(
            latency_snapshot=latency_snapshot,
            config=config,
        )
        rules.append(latency_rule)

    triggered_rules = [
        r["rule_id"] for r in rules if r["status"] == "TRIGGERED"
    ]

    if triggered_rules:
        eval_status = "TRIGGERED"
    elif total == 0:
        eval_status = "NO_DATA"
    elif total < config.min_total_requests:
        eval_status = "LOW_TRAFFIC"
    else:
        eval_status = "NORMAL"

    return {
        "index": snapshot.get("index", "app-logs-*"),
        "window_start": snapshot.get("window_start"),
        "window_end": snapshot.get("window_end"),
        "evaluation_status": eval_status,
        "triggered_rules": triggered_rules,
        "rules": rules,
    }
