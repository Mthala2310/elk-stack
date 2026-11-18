#!/usr/bin/env python3
"""
Synthetic Java Microservice Log Generator
AI-Enhanced Centralized Log Monitoring and Incident Analysis Platform

Produces structured logs matching Logstash Grok patterns:
- Pola A: Performance Metrics (Start / End with duration_ms)
- Pola B: Business Input Parameters (Input Variable Name: xxx -> yyy)
- Pola C: Opening Trace Span (Service->Step->)
- Pola D: General Exception / Fallback logs

Supported Condition Scenarios (--mode):
- normal: Normal successful transactions (DEBUG input variables, fast End durations 10-250ms)
- high_error_rate: Spikes of ERROR level logs to trigger HIGH_ERROR_LOG_RATE rule (>5% error rate)
- repeated_service_error: Repeated errors on a specific service/step (>15 errors) to trigger REPEATED_ERROR_ENDPOINT
- slow_latency: Step execution metrics with duration_ms > 4000ms to trigger HIGH_RESPONSE_TIME rule
- pola_d_exception: General Java exceptions with caller_class and no service_name
- mixed: Realistic mixed traffic (85% normal, 10% slow, 5% error)
"""

from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# Root folder project
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = str(PROJECT_ROOT / "logs" / "application.log")

JAKARTA_TZ = timezone(timedelta(hours=7))

# Contoh data service dan trace nyata
SERVICES = [
    "beneficiaryValidationNotification Ver. 7",
    "accountInquiryService Ver. 3",
    "paymentTransferService Ver. 5",
    "notificationDispatcher Ver. 2",
]

STEPS = ["prepare", "validate", "inquiryHost", "emailContent", "email", "auditLog"]

CALLERS = [
    ("main.Service", "prepareInput", 315),
    ("Performance", "close", 185),
    ("Performance", "unregisterContextForAsynch", 221),
    ("emailService.Sender", "send", 92),
    ("database.Connector", "execute", 410),
    ("com.bank.service.TransactionHandler", "process", 142),
    ("com.bank.service.PaymentProcessor", "executePayment", 88),
]

INPUT_VARIABLES = [
    ("validationStatusId", "1"),
    ("corpId", "CORP0091"),
    ("validationStatus", "SUCCESS"),
    ("currency", "IDR"),
    ("emailAddress", "customer@bank.example"),
    ("accountCurrency", "IDR"),
    ("makerUserId", "MAKER01"),
    ("amount", "1500000.00"),
    ("hostAccountNo", "8820194812"),
    ("hostAccountNm", "PT REKSA JAYA"),
]

EXCEPTION_MESSAGES = [
    "NullPointerException: Failed to resolve hostAccountNo for beneficiary context",
    "SocketTimeoutException: Connection timed out to SMTP mail.bank.internal:587",
    "SQLException: Connection pool exhausted after waiting 30000 ms",
    "ServiceUnavailableException: Host backend payment core returned HTTP 503",
    "ValidationException: Invalid instructionModeId supplied in payload",
]


def format_timestamp(dt: datetime) -> str:
    """Format: yyyy-MM-dd HH:mm:ss,SSS (WIB / Asia/Jakarta)"""
    return dt.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]


def generate_trace_id(rng: random.Random) -> str:
    """Generate realistic positive or negative Java integer trace_id"""
    return str(rng.randint(100000000, 999999999))


# =========================================================
# GENERATOR SKENARIO KONDISI
# =========================================================

def emit_normal_transaction(
    trace_id: str,
    service_name: str,
    rng: random.Random,
    dt_start: datetime,
) -> List[str]:
    """Menghasilkan 1 transaksi normal lengkap (Input params -> Start -> End step -> Selesai)"""
    lines = []
    curr_time = dt_start

    # 1. Input variables (DEBUG)
    sample_vars = rng.sample(INPUT_VARIABLES, k=rng.randint(3, 6))
    for var_name, var_val in sample_vars:
        line = (
            f"DEBUG {format_timestamp(curr_time)} main.Service(prepareInput:315) - "
            f"[{trace_id}][{service_name}]Input Variable Name: {var_name} -> {var_val}"
        )
        lines.append(line)
        curr_time += timedelta(milliseconds=rng.randint(1, 3))

    # 2. SLA Budget Start (Start [29998 ms])
    line_start = (
        f"INFO  {format_timestamp(curr_time)} Performance(close:185) - "
        f"[{trace_id}][{service_name}->Start]Start [29998 ms]"
    )
    lines.append(line_start)
    curr_time += timedelta(milliseconds=rng.randint(2, 5))

    # 3. Execution Steps
    steps_to_run = ["prepare", "validate", "email"]
    for step in steps_to_run:
        dur = rng.randint(5, 180)  # Cepat (5 - 180 ms)
        curr_time += timedelta(milliseconds=dur)
        line_end = (
            f"INFO  {format_timestamp(curr_time)} Performance(close:185) - "
            f"[{trace_id}][{service_name}->{step}]End [{dur} ms]"
        )
        lines.append(line_end)

    return lines


def emit_repeated_service_error(
    trace_id: str,
    service_name: str,
    target_step: str,
    rng: random.Random,
    dt_start: datetime,
) -> List[str]:
    """Menghasilkan error pada service dan step tertentu yang berulang kali gagal"""
    lines = []
    curr_time = dt_start

    # Log step yang gagal (ERROR)
    err_msg = rng.choice(EXCEPTION_MESSAGES)
    line_err = (
        f"ERROR {format_timestamp(curr_time)} emailService.Sender(send:92) - "
        f"[{trace_id}][{service_name}->{target_step}]{err_msg}"
    )
    lines.append(line_err)
    curr_time += timedelta(milliseconds=10)

    # Catat step End dengan durasi eksekusi
    line_end = (
        f"INFO  {format_timestamp(curr_time)} Performance(close:185) - "
        f"[{trace_id}][{service_name}->{target_step}]End [35 ms]"
    )
    lines.append(line_end)

    return lines


def emit_slow_latency_transaction(
    trace_id: str,
    service_name: str,
    target_step: str,
    rng: random.Random,
    dt_start: datetime,
) -> List[str]:
    """Menghasilkan transaksi dengan durasi eksekusi sangat lambat (> 4000 ms)"""
    lines = []
    curr_time = dt_start

    # Input variable
    line_var = (
        f"DEBUG {format_timestamp(curr_time)} main.Service(prepareInput:315) - "
        f"[{trace_id}][{service_name}]Input Variable Name: validationStatusId -> 1"
    )
    lines.append(line_var)
    curr_time += timedelta(milliseconds=5)

    # Durasi lambat di atas 4000 ms (misal 4200 - 6500 ms)
    slow_duration = rng.randint(4200, 6800)
    curr_time += timedelta(milliseconds=slow_duration)

    line_slow = (
        f"INFO  {format_timestamp(curr_time)} Performance(unregisterContextForAsynch:221) - "
        f"[{trace_id}][{service_name}->{target_step}]End [{slow_duration} ms]"
    )
    lines.append(line_slow)

    return lines


def emit_pola_d_exception(
    trace_id: str,
    rng: random.Random,
    dt_start: datetime,
) -> List[str]:
    """Menghasilkan baris error Pola D (hanya caller_class, tanpa service_name)"""
    lines = []
    caller_class, caller_method, caller_line = rng.choice(CALLERS[5:])
    err_msg = rng.choice(EXCEPTION_MESSAGES)

    line = (
        f"ERROR {format_timestamp(dt_start)} {caller_class}({caller_method}:{caller_line}) - "
        f"[{trace_id}] {err_msg}"
    )
    lines.append(line)
    return lines


# =========================================================
# CLI PARSER & RUNNER
# =========================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synthetic Java Microservice Log Generator for ELK Observability Platform"
    )
    parser.add_argument(
        "--mode",
        choices=[
            "normal",
            "high_error_rate",
            "repeated_service_error",
            "slow_latency",
            "pola_d_exception",
            "mixed",
        ],
        default="mixed",
        help="Skenario kondisi log yang dihasilkan (default: mixed)",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"File output target (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--service",
        default="beneficiaryValidationNotification Ver. 7",
        help="Nama microservice utama yang digunakan",
    )
    parser.add_argument(
        "--step",
        default="email",
        help="Nama step microservice target (default: email)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Interval jeda antar transaksi dalam detik (default: 0.5s)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Jumlah transaksi yang dihasilkan (0 = jalan terus menerus)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed integer untuk RNG reproduktif",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stop_requested = False

    def handle_signal(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print("=" * 60)
    print("JAVA MICROSERVICE LOG GENERATOR")
    print(f"Mode Kondisi : {args.mode}")
    print(f"Service Target: {args.service}")
    print(f"File Output  : {output_path}")
    print(f"Interval     : {args.interval}s")
    print(f"Target Count : {'Continuous (Tekan Ctrl+C untuk berhenti)' if args.count == 0 else args.count}")
    print("=" * 60)

    emitted_transactions = 0
    emitted_lines = 0

    with output_path.open("a", encoding="utf-8", buffering=1) as fh:
        while not stop_requested and (args.count == 0 or emitted_transactions < args.count):
            now = datetime.now(JAKARTA_TZ)
            trace_id = generate_trace_id(rng)
            mode = args.mode

            if mode == "mixed":
                roll = rng.random()
                if roll < 0.75:
                    chosen_mode = "normal"
                elif roll < 0.88:
                    chosen_mode = "slow_latency"
                elif roll < 0.95:
                    chosen_mode = "repeated_service_error"
                else:
                    chosen_mode = "pola_d_exception"
            else:
                chosen_mode = mode

            # Generate baris log sesuai mode
            if chosen_mode == "normal":
                batch = emit_normal_transaction(trace_id, args.service, rng, now)
            elif chosen_mode == "repeated_service_error":
                batch = emit_repeated_service_error(trace_id, args.service, args.step, rng, now)
            elif chosen_mode == "high_error_rate":
                batch = emit_repeated_service_error(trace_id, args.service, args.step, rng, now)
                # Tambah error ekstra untuk menaikkan error rate
                for _ in range(rng.randint(2, 4)):
                    batch.extend(emit_pola_d_exception(trace_id, rng, now))
            elif chosen_mode == "slow_latency":
                batch = emit_slow_latency_transaction(trace_id, args.service, args.step, rng, now)
            elif chosen_mode == "pola_d_exception":
                batch = emit_pola_d_exception(trace_id, rng, now)
            else:
                batch = emit_normal_transaction(trace_id, args.service, rng, now)

            # Tulis ke file dan print
            for line in batch:
                fh.write(line + "\n")
                print(line)
                emitted_lines += 1

            emitted_transactions += 1

            if args.interval > 0 and (args.count == 0 or emitted_transactions < args.count):
                time.sleep(args.interval)

    print("\n" + "=" * 60)
    print(f"[SELESAI] Total Transaksi: {emitted_transactions} | Total Baris Log: {emitted_lines}")
    print(f"Log tersimpan di: {output_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] Generator dihentikan pengguna.")
        sys.exit(0)

