#!/usr/bin/env python3
"""
Phase 1 - Synthetic HTTP Log Generator
AI-Enhanced Centralized Log Monitoring and Incident Analysis Platform

Contract followed from PRD / Project Hub:
IP - - [dd/MMM/yyyy:HH:mm:ss Z] "METHOD PATH HTTP/VERSION" STATUS SIZE_OR_DASH "REFERRER" "USER_AGENT" RESPONSE_TIME

Notes:
- Synthetic/anonymized values only.
- request_size can be "-" so Logstash normalization to 0 can be tested.
- referrer can be "-" so Logstash remove_field branch can be tested.
- response_time is emitted as a raw integer. Its real unit must be locked later
  before dashboard thresholds / incident rules are finalized.
"""

from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

JAKARTA_TZ = timezone(timedelta(hours=7))

MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

METHODS = ["GET", "GET", "GET", "POST", "PUT", "DELETE"]
HTTP_VERSIONS = ["1.1", "1.1", "1.1", "2.0"]

PATHS = [
    "/",
    "/health",
    "/api/login",
    "/api/logout",
    "/api/users",
    "/api/users/profile",
    "/api/orders",
    "/api/orders/checkout",
    "/api/products",
    "/api/products/search",
    "/api/payments",
    "/api/report",
]

USER_AGENTS = [
    "Mozilla/5.0 (Synthetic Chrome Client)",
    "Mozilla/5.0 (Synthetic Firefox Client)",
    "curl/8.5.0 synthetic-client",
    "PostmanRuntime/7.43.0 synthetic-client",
    "Synthetic-Mobile-App/1.0",
]

REFERRERS = [
    "https://example.test/",
    "https://example.test/dashboard",
    "https://example.test/login",
    "https://example.test/products",
]

DOC_IP_PREFIXES = [
    "192.0.2",      # TEST-NET-1
    "198.51.100",   # TEST-NET-2
    "203.0.113",    # TEST-NET-3
]

NORMAL_2XX = [200, 200, 200, 200, 201, 204]
NORMAL_3XX = [301, 302, 304]
ERROR_4XX = [400, 401, 403, 404, 408, 416, 429]
ERROR_5XX = [500, 500, 502, 503, 504]


@dataclass
class Event:
    ip_addr: str
    timestamp: datetime
    http_method: str
    request_path: str
    http_version: str
    status_code: int
    request_size: Optional[int]
    referrer: Optional[str]
    user_agent: str
    response_time: Optional[int]


def apache_timestamp(dt: datetime) -> str:
    """Locale-independent dd/MMM/yyyy:HH:mm:ss Z formatter."""
    offset = dt.strftime("%z")
    return (
        f"{dt.day:02d}/{MONTHS[dt.month]}/{dt.year:04d}:"
        f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {offset}"
    )


def synthetic_ip(rng: random.Random) -> str:
    return f"{rng.choice(DOC_IP_PREFIXES)}.{rng.randint(1, 254)}"


def choose_status(mode: str, rng: random.Random) -> int:
    x = rng.random()

    if mode == "normal":
        if x < 0.82:
            return rng.choice(NORMAL_2XX)
        if x < 0.90:
            return rng.choice(NORMAL_3XX)
        if x < 0.985:
            return rng.choice(ERROR_4XX)
        return rng.choice(ERROR_5XX)

    if mode == "4xx-spike":
        if x < 0.68:
            return rng.choice(ERROR_4XX)
        if x < 0.94:
            return rng.choice(NORMAL_2XX)
        if x < 0.97:
            return rng.choice(NORMAL_3XX)
        return rng.choice(ERROR_5XX)

    if mode == "5xx-spike":
        if x < 0.62:
            return rng.choice(ERROR_5XX)
        if x < 0.91:
            return rng.choice(NORMAL_2XX)
        if x < 0.96:
            return rng.choice(ERROR_4XX)
        return rng.choice(NORMAL_3XX)

    if mode == "slow-response":
        # Slow-response mode changes latency distribution, not necessarily HTTP status.
        if x < 0.84:
            return rng.choice(NORMAL_2XX)
        if x < 0.91:
            return rng.choice(NORMAL_3XX)
        if x < 0.985:
            return rng.choice(ERROR_4XX)
        return rng.choice(ERROR_5XX)

    if mode == "mixed":
        # Balanced demo traffic containing normal, client error, server error, and slow events.
        if x < 0.52:
            return rng.choice(NORMAL_2XX)
        if x < 0.60:
            return rng.choice(NORMAL_3XX)
        if x < 0.80:
            return rng.choice(ERROR_4XX)
        return rng.choice(ERROR_5XX)

    raise ValueError(f"Unsupported mode: {mode}")


def choose_path(status: int, rng: random.Random) -> str:
    if status >= 500:
        return rng.choice([
            "/api/payments",
            "/api/orders/checkout",
            "/api/report",
            "/api/products/search",
        ])
    if status in (401, 403):
        return rng.choice(["/api/login", "/api/users/profile", "/api/report"])
    if status == 404:
        return rng.choice([
            "/api/unknown",
            "/api/products/missing",
            "/assets/missing.js",
        ])
    return rng.choice(PATHS)


def choose_response_time(mode: str, status: int, rng: random.Random) -> int:
    # Deliberately raw numeric units until response_time semantics are confirmed.
    if mode == "slow-response":
        return rng.randint(3000, 12000)

    if mode == "mixed" and rng.random() < 0.22:
        return rng.randint(3000, 12000)

    if status >= 500:
        return rng.randint(900, 5000)

    if status >= 400:
        return rng.randint(150, 1800)

    return rng.randint(40, 300)


def build_event(
    mode: str,
    rng: random.Random,
    dash_size_rate: float,
    dash_referrer_rate: float,
    omit_response_time_rate: float,
) -> Event:
    status = choose_status(mode, rng)

    request_size: Optional[int]
    if rng.random() < dash_size_rate:
        request_size = None
    else:
        request_size = rng.randint(0, 16384)

    referrer: Optional[str]
    if rng.random() < dash_referrer_rate:
        referrer = None
    else:
        referrer = rng.choice(REFERRERS)

    response_time: Optional[int]
    if rng.random() < omit_response_time_rate:
        response_time = None
    else:
        response_time = choose_response_time(mode, status, rng)

    return Event(
        ip_addr=synthetic_ip(rng),
        timestamp=datetime.now(JAKARTA_TZ),
        http_method=rng.choice(METHODS),
        request_path=choose_path(status, rng),
        http_version=rng.choice(HTTP_VERSIONS),
        status_code=status,
        request_size=request_size,
        referrer=referrer,
        user_agent=rng.choice(USER_AGENTS),
        response_time=response_time,
    )


def format_event(event: Event) -> str:
    size = "-" if event.request_size is None else str(event.request_size)
    referrer = "-" if event.referrer is None else event.referrer

    base = (
        f'{event.ip_addr} - - [{apache_timestamp(event.timestamp)}] '
        f'"{event.http_method} {event.request_path} HTTP/{event.http_version}" '
        f'{event.status_code} {size} "{referrer}" "{event.user_agent}"'
    )

    if event.response_time is not None:
        base += f" {event.response_time}"

    return base


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthetic HTTP log generator")
    parser.add_argument(
        "--mode",
        choices=["normal", "4xx-spike", "5xx-spike", "slow-response", "mixed"],
        default="normal",
    )
    parser.add_argument(
        "--output",
        default="logs/application.log",
        help="Output log file path (default: logs/application.log)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Seconds between events (default: 0.5)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Number of events. 0 = continuous until Ctrl+C (default: 0)",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--dash-size-rate",
        type=float,
        default=0.08,
        help='Probability request_size becomes "-" (default: 0.08)',
    )
    parser.add_argument(
        "--dash-referrer-rate",
        type=float,
        default=0.35,
        help='Probability referrer becomes "-" (default: 0.35)',
    )
    parser.add_argument(
        "--omit-response-time-rate",
        type=float,
        default=0.03,
        help="Probability response_time is omitted (default: 0.03)",
    )
    return parser.parse_args()


def validate_probability(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


def main() -> int:
    args = parse_args()

    validate_probability("--dash-size-rate", args.dash_size_rate)
    validate_probability("--dash-referrer-rate", args.dash_referrer_rate)
    validate_probability("--omit-response-time-rate", args.omit_response_time_rate)

    if args.interval < 0:
        raise ValueError("--interval must be >= 0")
    if args.count < 0:
        raise ValueError("--count must be >= 0")

    rng = random.Random(args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    stop_requested = False

    def handle_signal(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(
        f"[generator] mode={args.mode} output={output} "
        f"interval={args.interval}s count={'continuous' if args.count == 0 else args.count}"
    )

    emitted = 0
    with output.open("a", encoding="utf-8", buffering=1) as fh:
        while not stop_requested and (args.count == 0 or emitted < args.count):
            event = build_event(
                args.mode,
                rng,
                args.dash_size_rate,
                args.dash_referrer_rate,
                args.omit_response_time_rate,
            )
            line = format_event(event)
            fh.write(line + "\n")
            print(line)
            emitted += 1

            if args.interval > 0 and (args.count == 0 or emitted < args.count):
                time.sleep(args.interval)

    print(f"\n[generator] stopped. emitted={emitted}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[generator] configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2)
