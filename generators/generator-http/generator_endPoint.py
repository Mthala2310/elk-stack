#!/usr/bin/env python3
"""
Custom HTTP Log Generator
AI-Enhanced Centralized Log Monitoring and Incident Analysis Platform

Mendukung fleksibilitas penuh untuk menentukan:
- Endpoint target (--path) : satu path, beberapa path dipisah koma, atau seluruh path default.
- Status target (--status)  : kategori (normal, 2xx, 3xx, error4xx, 4xx, error5xx, 5xx) 
                             maupun kode HTTP spesifik (misal: 200, 404, 500) dipisah koma.
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
from typing import List, Optional

JAKARTA_TZ = timezone(timedelta(hours=7))

MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

DEFAULT_PATHS = [
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

ENDPOINT_METHODS = {
    "/": ["GET"],
    "/health": ["GET"],
    "/api/login": ["POST"],
    "/api/logout": ["POST"],
    "/api/users": ["GET", "POST"],
    "/api/users/profile": ["GET", "PUT"],
    "/api/orders": ["GET", "POST"],
    "/api/orders/checkout": ["POST"],
    "/api/products": ["GET"],
    "/api/products/search": ["GET"],
    "/api/payments": ["POST"],
    "/api/report": ["GET"],
}

HTTP_VERSIONS = ["1.1", "1.1", "1.1", "2.0"]

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

STATUS_GROUPS = {
    "normal": [200, 200, 200, 200, 201, 204],
    "2xx": [200, 201, 204],
    "3xx": [301, 302, 304],
    "error4xx": [400, 401, 403, 404, 408, 416, 429],
    "4xx": [400, 401, 403, 404, 408, 416, 429],
    "error5xx": [500, 500, 502, 503, 504],
    "5xx": [500, 502, 503, 504],
}


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
    offset = dt.strftime("%z")
    return (
        f"{dt.day:02d}/{MONTHS[dt.month]}/{dt.year:04d}:"
        f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {offset}"
    )


def synthetic_ip(rng: random.Random) -> str:
    return f"{rng.choice(DOC_IP_PREFIXES)}.{rng.randint(1, 254)}"


def choose_method(path: str, rng: random.Random) -> str:
    if path in ENDPOINT_METHODS:
        return rng.choice(ENDPOINT_METHODS[path])
    return rng.choice(["GET", "POST", "PUT", "DELETE"])


def parse_status_argument(status_arg: str) -> List[int]:
    """Mengubah input status string dipisah koma menjadi list kode status HTTP."""
    tokens = [t.strip().lower() for t in status_arg.split(",") if t.strip()]
    resolved_statuses: List[int] = []

    for token in tokens:
        if token in STATUS_GROUPS:
            resolved_statuses.extend(STATUS_GROUPS[token])
        elif token.isdigit():
            resolved_statuses.append(int(token))
        else:
            valid_keys = list(STATUS_GROUPS.keys())
            raise ValueError(
                f"Kategori/kode status '{token}' tidak valid. "
                f"Pilihan kategori: {valid_keys} atau masukkan angka kode HTTP langsung (misal: 200, 404, 500)."
            )

    if not resolved_statuses:
        return STATUS_GROUPS["normal"]
    return resolved_statuses


def choose_response_time(status: int, rng: random.Random) -> int:
    """Menghitung response_time yang realistis berdasarkan status code."""
    if status >= 500:
        return rng.randint(900, 5000)
    if status >= 400:
        return rng.randint(150, 1800)
    if status >= 300:
        return rng.randint(50, 400)
    return rng.randint(40, 300)


def build_event(
    path: str,
    status_pool: List[int],
    rng: random.Random,
    dash_size_rate: float,
    dash_referrer_rate: float,
    omit_response_time_rate: float,
) -> Event:
    status = rng.choice(status_pool)

    request_size: Optional[int]
    if rng.random() < dash_size_rate:
        request_size = None
    else:
        request_size = rng.randint(100, 16384)

    referrer: Optional[str]
    if rng.random() < dash_referrer_rate:
        referrer = None
    else:
        referrer = rng.choice(REFERRERS)

    response_time: Optional[int]
    if rng.random() < omit_response_time_rate:
        response_time = None
    else:
        response_time = choose_response_time(status, rng)

    return Event(
        ip_addr=synthetic_ip(rng),
        timestamp=datetime.now(JAKARTA_TZ),
        http_method=choose_method(path, rng),
        request_path=path,
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
    parser = argparse.ArgumentParser(
        description="Flexible HTTP Log Generator (Custom Path & Status)"
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Endpoint target. Bisa 1 endpoint (/api/report) atau beberapa dipisah koma (/api/report,/api/orders).",
    )
    # Mendukung --status dan alias --stautus (mengantisipasi typo umum)
    parser.add_argument(
        "--status",
        "--stautus",
        dest="status",
        type=str,
        default="normal",
        help="Status target. Kategori: normal, error4xx, error5xx, 2xx, 3xx, 4xx, 5xx atau angka (misal: 200,404,500). Pisahkan dengan koma.",
    )
    parser.add_argument(
        "--output",
        default="logs/application.log",
        help="Lokasi file output log (default: logs/application.log)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Jeda waktu antar log dalam detik (default: 0.5)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Jumlah total log. 0 = berjalan terus menerus (default: 0)",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--dash-size-rate",
        type=float,
        default=0.08,
        help='Probabilitas request_size bernilai "-" (default: 0.08)',
    )
    parser.add_argument(
        "--dash-referrer-rate",
        type=float,
        default=0.35,
        help='Probabilitas referrer bernilai "-" (default: 0.35)',
    )
    parser.add_argument(
        "--omit-response-time-rate",
        type=float,
        default=0.03,
        help="Probabilitas response_time dihilangkan (default: 0.03)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.interval < 0 or args.count < 0:
        raise ValueError("interval dan count harus >= 0")

    # Parsing endpoint target
    if args.path:
        paths = [p.strip() for p in args.path.split(",") if p.strip()]
    else:
        paths = DEFAULT_PATHS

    # Parsing status pool
    status_pool = parse_status_argument(args.status)

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
        f"[custom-generator] paths={paths} status_sample={sorted(list(set(status_pool)))} "
        f"output={output} interval={args.interval}s count={'continuous' if args.count == 0 else args.count}"
    )

    emitted = 0
    path_index = 0
    total_paths = len(paths)

    with output.open("a", encoding="utf-8", buffering=1) as fh:
        while not stop_requested and (args.count == 0 or emitted < args.count):
            selected_path = paths[path_index]
            path_index = (path_index + 1) % total_paths

            event = build_event(
                selected_path,
                status_pool,
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

    print(f"\n[custom-generator] stopped. emitted={emitted}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[custom-generator] error: {exc}", file=sys.stderr)
        raise SystemExit(2)
