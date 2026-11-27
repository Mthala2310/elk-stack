#!/usr/bin/env python3
"""
Enterprise Java Microservice Distributed Tracing Log Generator
AI-Enhanced Centralized Log Monitoring and Incident Analysis Platform

Simulates real-world enterprise banking and fintech distributed microservices
with realistic multi-service transactions, span hierarchies, business input parameters,
and diverse failure modes conforming to Logstash Grok patterns (Pola A, B, C, D).

Supported Modes / Scenarios (--mode):
- realistic (default)    : 92% normal enterprise traffic across diverse workflows,
                           5% slow/degraded steps (e.g. partner timeout/network lag),
                           3% realistic business & technical exceptions.
- normal                 : 100% clean successful transactions with fast execution (5-150ms).
- high_error_rate        : Sudden surge of errors (>15%) to trigger HIGH_ERROR_LOG_RATE rule.
- repeated_service_error : High frequency repeated errors on a specific service/step (>15 errors)
                           to trigger REPEATED_ERROR_ENDPOINT rule.
- slow_latency           : Step execution metrics with duration_ms > 4000ms (e.g. 4200-6800ms)
                           to trigger HIGH_RESPONSE_TIME rule.
- core_timeout           : Core Banking Host timeout & socket disconnection failures.
- db_exhaustion          : Database connection pool (HikariCP) exhaustion failures.
- circuit_breaker        : Resilience4j circuit breaker trip & open fallback state.
- business_errors        : Business logic rejections (Insufficient funds, Dormant accounts).
- mixed                  : Backward-compatible alias for 'realistic'.
- pola_d_exception       : Uncaught JVM exceptions without service_name header.
"""

from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

# Root folder project
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = str(PROJECT_ROOT / "logs" / "application.log")

JAKARTA_TZ = timezone(timedelta(hours=7))


# =====================================================================
# 1. ENTERPRISE TOPOLOGY & MICROSERVICES CATALOG
# =====================================================================

MICROSERVICES: Dict[str, Dict[str, Any]] = {
    "authService Ver. 4": {
        "callers": [
            ("com.bank.gateway.auth.SecurityTokenValidator", "validateSession", 112),
            ("com.bank.gateway.auth.OAuth2ResourceServer", "authenticateBearerToken", 84),
            ("com.bank.gateway.auth.ClientContextResolver", "resolveContext", 55),
        ],
        "steps": ["validateToken", "checkPermissions", "resolveClientContext"],
        "avg_duration": (5, 25),
    },
    "accountInquiryService Ver. 3": {
        "callers": [
            ("com.bank.account.service.BalanceInquiryService", "checkAvailableBalance", 204),
            ("com.bank.account.repository.AccountRepository", "findByCifAndCurrency", 95),
            ("com.bank.account.client.CoreHostAccountClient", "fetchHoldBalances", 148),
        ],
        "steps": ["inquiryBalance", "checkCIFStatus", "verifyHoldBalance"],
        "avg_duration": (15, 60),
    },
    "beneficiaryValidationService Ver. 7": {
        "callers": [
            ("com.bank.payment.bifast.BiFastRoutingClient", "routeTransfer", 88),
            ("com.bank.beneficiary.validator.ProxyResolver", "resolveProxyAddress", 132),
            ("com.bank.beneficiary.client.CentralBankClearingClient", "inquireBeneficiaryName", 64),
        ],
        "steps": ["proxyResolution", "routingLookup", "nameValidation"],
        "avg_duration": (30, 120),
    },
    "fraudDetectionEngine Ver. 1": {
        "callers": [
            ("com.bank.fraud.engine.RiskScoreCalculator", "evaluateTransactionVelocity", 175),
            ("com.bank.fraud.rules.DeviceFingerprintMatcher", "checkDeviceTrust", 92),
            ("com.bank.fraud.scoring.AmlSanctionChecker", "screenBlacklist", 210),
        ],
        "steps": ["velocityCheck", "deviceTrustScore", "amlSanctionScreening"],
        "avg_duration": (20, 85),
    },
    "fundTransferCoreService Ver. 5": {
        "callers": [
            ("com.bank.core.ledger.CoreBankingPostingClient", "postJournalEntry", 320),
            ("com.bank.core.service.FundTransferCoordinator", "executeDebitCredit", 215),
            ("com.bank.core.repository.LedgerReservationRepo", "reserveFunds", 108),
        ],
        "steps": ["reserveFunds", "coreHostDebit", "coreHostCredit", "settleJournal"],
        "avg_duration": (40, 160),
    },
    "paymentGatewayService Ver. 2": {
        "callers": [
            ("com.bank.payment.qris.MerchantAcquirerService", "processPayment", 142),
            ("com.bank.payment.qris.QrParser", "parseDynamicQrPayload", 76),
            ("com.bank.payment.settlement.MerchantFeeCalculator", "computeMdrFee", 118),
        ],
        "steps": ["parseQrPayload", "verifyMerchantNmid", "calculateMdr", "settleMerchant"],
        "avg_duration": (15, 70),
    },
    "vaManagementService Ver. 2": {
        "callers": [
            ("com.bank.va.billing.VirtualAccountManager", "settleBill", 180),
            ("com.bank.va.client.BillerWebhookClient", "notifyBillerPayment", 145),
            ("com.bank.va.validator.VaRangeValidator", "validateVaPrefix", 58),
        ],
        "steps": ["validateVaPrefix", "inquiryBillDetails", "settleBillingInvoice", "notifyBiller"],
        "avg_duration": (25, 90),
    },
    "notificationDispatcher Ver. 2": {
        "callers": [
            ("com.bank.notification.dispatcher.NotificationRouter", "dispatchReceipt", 94),
            ("com.bank.notification.mail.SmtpClient", "sendEmailReceipt", 82),
            ("com.bank.notification.fcm.FirebasePushClient", "sendPushNotification", 126),
        ],
        "steps": ["renderTemplate", "sendEmail", "sendPushNotif"],
        "avg_duration": (10, 50),
    },
    "auditComplianceService Ver. 1": {
        "callers": [
            ("com.bank.audit.compliance.AuditTrailLogger", "persistAuditRecord", 65),
            ("com.bank.audit.storage.ImmutableLedgerStore", "appendAuditLog", 110),
        ],
        "steps": ["buildAuditPayload", "persistAuditJournal"],
        "avg_duration": (8, 35),
    },
}

# Standard performance callers for Start & End metrics (Pola A)
PERF_CALLERS = [
    ("Performance", "close", 185),
    ("Performance", "unregisterContextForAsynch", 221),
    ("com.bank.framework.performance.PerformanceTracker", "close", 185),
]

# Standard span opener callers (Pola C)
SPAN_OPENER_CALLERS = [
    ("com.bank.context.TraceContextManager", "openSpan", 114),
    ("main.Service", "openSpan", 114),
]


# =====================================================================
# 2. REALISTIC ENTERPRISE TRANSACTION WORKFLOWS
# =====================================================================

WORKFLOWS: Dict[str, Dict[str, Any]] = {
    "BI_FAST_TRANSFER": {
        "desc": "BI-FAST Real-time Interbank Fund Transfer",
        "steps": [
            ("authService Ver. 4", "validateToken"),
            ("accountInquiryService Ver. 3", "inquiryBalance"),
            ("beneficiaryValidationService Ver. 7", "routingLookup"),
            ("fraudDetectionEngine Ver. 1", "velocityCheck"),
            ("fundTransferCoreService Ver. 5", "reserveFunds"),
            ("fundTransferCoreService Ver. 5", "coreHostDebit"),
            ("beneficiaryValidationService Ver. 7", "proxyResolution"),
            ("fundTransferCoreService Ver. 5", "settleJournal"),
            ("notificationDispatcher Ver. 2", "sendPushNotif"),
            ("auditComplianceService Ver. 1", "persistAuditJournal"),
        ],
    },
    "QRIS_PAYMENT": {
        "desc": "QRIS Dynamic Merchant Acquirer Payment",
        "steps": [
            ("authService Ver. 4", "validateToken"),
            ("paymentGatewayService Ver. 2", "parseQrPayload"),
            ("paymentGatewayService Ver. 2", "verifyMerchantNmid"),
            ("accountInquiryService Ver. 3", "inquiryBalance"),
            ("fraudDetectionEngine Ver. 1", "deviceTrustScore"),
            ("fundTransferCoreService Ver. 5", "coreHostDebit"),
            ("paymentGatewayService Ver. 2", "settleMerchant"),
            ("notificationDispatcher Ver. 2", "sendPushNotif"),
            ("auditComplianceService Ver. 1", "persistAuditJournal"),
        ],
    },
    "VIRTUAL_ACCOUNT_PAYMENT": {
        "desc": "Virtual Account (E-Commerce/Billing) Instant Settlement",
        "steps": [
            ("vaManagementService Ver. 2", "validateVaPrefix"),
            ("vaManagementService Ver. 2", "inquiryBillDetails"),
            ("accountInquiryService Ver. 3", "inquiryBalance"),
            ("fundTransferCoreService Ver. 5", "coreHostDebit"),
            ("vaManagementService Ver. 2", "notifyBiller"),
            ("notificationDispatcher Ver. 2", "sendEmail"),
            ("auditComplianceService Ver. 1", "persistAuditJournal"),
        ],
    },
    "ACCOUNT_STATEMENT_INQUIRY": {
        "desc": "Customer Account Portfolio & Balance Inquiry",
        "steps": [
            ("authService Ver. 4", "validateToken"),
            ("accountInquiryService Ver. 3", "checkCIFStatus"),
            ("accountInquiryService Ver. 3", "inquiryBalance"),
            ("accountInquiryService Ver. 3", "verifyHoldBalance"),
            ("auditComplianceService Ver. 1", "persistAuditJournal"),
        ],
    },
    "BATCH_PAYROLL_DISBURSEMENT": {
        "desc": "Corporate Multi-Account Payroll Disbursement",
        "steps": [
            ("authService Ver. 4", "validateToken"),
            ("accountInquiryService Ver. 3", "checkCIFStatus"),
            ("accountInquiryService Ver. 3", "inquiryBalance"),
            ("fundTransferCoreService Ver. 5", "reserveFunds"),
            ("fundTransferCoreService Ver. 5", "coreHostDebit"),
            ("fundTransferCoreService Ver. 5", "coreHostCredit"),
            ("fundTransferCoreService Ver. 5", "settleJournal"),
            ("notificationDispatcher Ver. 2", "sendEmail"),
            ("auditComplianceService Ver. 1", "persistAuditJournal"),
        ],
    },
}


# =====================================================================
# 3. ENTERPRISE BUSINESS ATTRIBUTES & INPUT VARIABLES
# =====================================================================

CHANNELS = ["MOBILE_BANKING", "INTERNET_BANKING_BIZ", "OPEN_API", "QRIS_TERMINAL", "ATM_NETWORK"]
CURRENCIES = ["IDR", "USD", "SGD"]
CORP_IDS = ["CORP_BCA_01", "CORP_MANDIRI_77", "INDOMARET_HO_01", "TOKOPEDIA_PAY_09", "TELKOMSEL_CORP", "ASTRA_INT_05"]
DEST_BANKS = ["BBBAIDJA", "BMRIIDJA", "BNINIDJA", "BRINIDJA", "CIMBIDJA", "BDINIDJA"]
BI_FAST_ROUTES = ["BIFAST-GW-JKT01", "BIFAST-GW-JKT02", "BIFAST-GW-SBY01", "BIFAST-GW-BDG01"]
MERCHANTS = [
    ("MID_INDOMARET_0192", "PT Indomarco Prismatama"),
    ("MID_TOKOPEDIA_8819", "PT Tokopedia"),
    ("MID_STARBUCKS_4401", "PT Sari Coffee Indonesia"),
    ("MID_ALFAMART_5510", "PT Sumber Alfaria Trijaya"),
    ("MID_KAI_ACCESS_991", "PT Kereta Api Indonesia"),
]


def generate_business_context(rng: random.Random) -> Dict[str, str]:
    """Menghasilkan pasangan parameter bisnis realistis untuk sebuah transaksi"""
    cif_id = f"CIF-{rng.randint(10000000, 99999999)}"
    corp_id = rng.choice(CORP_IDS)
    channel = rng.choice(CHANNELS)
    src_acc = f"88{rng.randint(10000000, 99999999)}"
    dst_acc = f"77{rng.randint(10000000, 99999999)}"
    dst_bank = rng.choice(DEST_BANKS)
    currency = "IDR" if rng.random() < 0.9 else rng.choice(["USD", "SGD"])

    amounts = [
        "25000.00", "50000.00", "150000.00", "500000.00",
        "1250000.00", "2500000.00", "15000000.00", "75000000.00"
    ]
    amount = rng.choice(amounts)
    fee = "2500.00" if channel == "MOBILE_BANKING" else "0.00"

    mid, mname = rng.choice(MERCHANTS)
    client_ip = f"{rng.randint(36, 182)}.{rng.randint(10, 250)}.{rng.randint(1, 250)}.{rng.randint(1, 250)}"
    device_id = f"DEV-{rng.choice(['ANDR', 'IOS'])}-{rng.randint(100000, 999999):X}"

    return {
        "cifNumber": cif_id,
        "corpId": corp_id,
        "channelId": channel,
        "sourceAccountNo": src_acc,
        "beneficiaryAccountNo": dst_acc,
        "beneficiaryBankCode": dst_bank,
        "biFastRoutingCode": rng.choice(BI_FAST_ROUTES),
        "transferAmount": amount,
        "feeAmount": fee,
        "currency": currency,
        "merchantId": mid,
        "merchantName": mname,
        "qrisTerminalId": f"TID_POS_{rng.randint(10000, 99999)}",
        "clientIp": client_ip,
        "deviceId": device_id,
        "riskScore": str(rng.randint(5, 45)),
        "validationStatus": "SUCCESS",
    }


# =====================================================================
# 4. REALISTIC ENTERPRISE EXCEPTIONS & FAILURE SIGNATURES
# =====================================================================

EXCEPTION_CATALOG: Dict[str, List[str]] = {
    "core_timeout": [
        "SocketTimeoutException: Read timed out connecting to Core Banking Host (10.20.44.12:9000) after 30000 ms",
        "HostGatewayTimeoutException: TCP handshake timed out to Mainframe AS400 after 15000 ms",
        "ConnectionResetException: Core Banking Host connection reset by peer during posting journal",
    ],
    "db_exhaustion": [
        "SQLException: HikariPool-Core - Connection is not available, request timed out after 30000ms (total=50, active=50, idle=0, waiting=142)",
        "CannotAcquireLockException: Lock wait timeout exceeded trying to execute ledger reservation on table TB_ACCOUNT_HOLD",
        "DataAccessResourceFailureException: Unable to acquire JDBC Connection from primary cluster (10.10.20.15:5432)",
    ],
    "circuit_breaker": [
        "CircuitBreakerOpenException: CircuitBreaker 'BiFastGateway' is OPEN and does not permit further calls (failureRate: 68.4% >= 50.0%)",
        "CallNotPermittedException: CircuitBreaker 'CentralBankClearingClient' is OPEN - fallback activated",
        "BulkheadFullException: Bulkhead 'fundTransferCore' is FULL and does not permit further calls (maxConcurrentCalls: 100)",
    ],
    "business_errors": [
        "InsufficientFundsException: Available balance (IDR 450,000.00) is insufficient for transaction amount + fee",
        "BeneficiaryAccountNotFoundException: Account rejected by receiving bank BMRIIDJA: 'ACCOUNT_DORMANT_OR_CLOSED'",
        "DailyLimitExceededException: Transaction amount exceeds daily transfer limit of IDR 100,000,000.00 for channel MOBILE_BANKING",
        "InvalidAccountStatusException: Source account is in FROZEN status due to AML compliance hold",
        "FraudScoreExceededException: Risk score (89/100) exceeded maximum allowable threshold (70/100) - Velocity anomaly detected",
    ],
    "general": [
        "NullPointerException: Target CIF context could not be dereferenced from Redis session cache",
        "RedisConnectionException: Unable to connect to Redis Sentinel cluster (10.10.15.20:26379) - Read timed out",
        "SmtpDeliveryException: Failed to send transaction receipt to customer@example.com - 421 4.7.0 Connection rate limit exceeded",
        "InvalidSecurityTokenException: JWT token signature expired at 2026-11-20T08:12:00Z",
    ],
}


# =====================================================================
# 5. LOG EMISSION FORMATTERS (CONFORMING TO LOGSTASH GROK)
# =====================================================================

def format_timestamp(dt: datetime) -> str:
    """Format: yyyy-MM-dd HH:mm:ss,SSS (WIB / Asia/Jakarta)"""
    return dt.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]


def generate_trace_id(rng: random.Random) -> str:
    """Generate realistic 9-digit Java integer trace_id"""
    return str(rng.randint(100000000, 999999999))


def format_pola_a_start(
    trace_id: str,
    service_name: str,
    step_name: str,
    dt: datetime,
    budget_ms: int = 29998,
    caller: Tuple[str, str, int] = ("Performance", "close", 185),
) -> str:
    """Pola A: Baris Metrik SLA Start"""
    c_cls, c_mth, c_line = caller
    return (
        f"INFO  {format_timestamp(dt)} {c_cls}({c_mth}:{c_line}) - "
        f"[{trace_id}][{service_name}->{step_name}]Start [{budget_ms} ms]"
    )


def format_pola_a_end(
    trace_id: str,
    service_name: str,
    step_name: str,
    duration_ms: int,
    dt: datetime,
    caller: Tuple[str, str, int] = ("Performance", "close", 185),
) -> str:
    """Pola A: Baris Metrik End dengan durasi eksekusi"""
    c_cls, c_mth, c_line = caller
    return (
        f"INFO  {format_timestamp(dt)} {c_cls}({c_mth}:{c_line}) - "
        f"[{trace_id}][{service_name}->{step_name}]End [{duration_ms} ms]"
    )


def format_pola_b_input_var(
    trace_id: str,
    service_name: str,
    var_name: str,
    var_value: str,
    dt: datetime,
    caller: Tuple[str, str, int] = ("main.Service", "prepareInput", 315),
) -> str:
    """Pola B: Parameter Input Bisnis"""
    c_cls, c_mth, c_line = caller
    return (
        f"DEBUG {format_timestamp(dt)} {c_cls}({c_mth}:{c_line}) - "
        f"[{trace_id}][{service_name}]Input Variable Name: {var_name} -> {var_value}"
    )


def format_pola_c_span_open(
    trace_id: str,
    service_name: str,
    step_name: str,
    dt: datetime,
    caller: Tuple[str, str, int] = ("com.bank.context.TraceContextManager", "openSpan", 114),
) -> str:
    """Pola C: Span Opening Trace"""
    c_cls, c_mth, c_line = caller
    return (
        f"INFO  {format_timestamp(dt)} {c_cls}({c_mth}:{c_line}) - "
        f"[{trace_id}][{service_name}->{step_name}-> "
    )


def format_pola_d_error(
    trace_id: str,
    service_name: Optional[str],
    step_name: Optional[str],
    exception_msg: str,
    dt: datetime,
    caller: Tuple[str, str, int] = ("database.Connector", "execute", 410),
) -> str:
    """Pola D / Error with optional service & step context"""
    c_cls, c_mth, c_line = caller
    if service_name and step_name:
        return (
            f"ERROR {format_timestamp(dt)} {c_cls}({c_mth}:{c_line}) - "
            f"[{trace_id}][{service_name}->{step_name}]{exception_msg}"
        )
    elif service_name:
        return (
            f"ERROR {format_timestamp(dt)} {c_cls}({c_mth}:{c_line}) - "
            f"[{trace_id}][{service_name}]{exception_msg}"
        )
    else:
        return (
            f"ERROR {format_timestamp(dt)} {c_cls}({c_mth}:{c_line}) - "
            f"[{trace_id}] {exception_msg}"
        )


# =====================================================================
# 6. DISTRIBUTED TRANSACTION GENERATION LOGIC
# =====================================================================

def emit_enterprise_transaction(
    trace_id: str,
    workflow_key: str,
    rng: random.Random,
    dt_start: datetime,
    scenario: str = "normal",
    override_service: Optional[str] = None,
    override_step: Optional[str] = None,
) -> Tuple[List[str], datetime]:
    """
    Menghasilkan satu transaksi terdistribusi multi-microservice lengkap.
    Mengembalikan: (daftar baris log, waktu selesai transaksi)
    """
    lines: List[str] = []
    curr_time = dt_start
    wf = WORKFLOWS[workflow_key]
    biz_context = generate_business_context(rng)

    # 1. Pilih subset input variables yang relevan untuk transaksi ini
    var_keys = rng.sample(list(biz_context.keys()), k=rng.randint(4, 7))

    # Tentukan apakah ada failure di skenario ini
    fail_at_step_idx: Optional[int] = None
    slow_step_idx: Optional[int] = None
    fail_exception: Optional[str] = None

    if scenario == "high_error_rate":
        # Pastikan gagal di salah satu step
        fail_at_step_idx = rng.randint(0, len(wf["steps"]) - 1)
        fail_exception = rng.choice(EXCEPTION_CATALOG["core_timeout"] + EXCEPTION_CATALOG["general"])
    elif scenario == "repeated_service_error":
        # Targetkan service & step override
        for idx, (svc, stp) in enumerate(wf["steps"]):
            if (override_service is None or override_service in svc) and (override_step is None or override_step in stp):
                fail_at_step_idx = idx
                break
        if fail_at_step_idx is None:
            fail_at_step_idx = len(wf["steps"]) - 1
        fail_exception = rng.choice(
            EXCEPTION_CATALOG["core_timeout"] + EXCEPTION_CATALOG["db_exhaustion"] + EXCEPTION_CATALOG["circuit_breaker"]
        )
    elif scenario == "slow_latency":
        slow_step_idx = rng.randint(1, len(wf["steps"]) - 2)
    elif scenario == "core_timeout":
        fail_at_step_idx = len(wf["steps"]) - 3
        fail_exception = rng.choice(EXCEPTION_CATALOG["core_timeout"])
    elif scenario == "db_exhaustion":
        fail_at_step_idx = rng.randint(1, 3)
        fail_exception = rng.choice(EXCEPTION_CATALOG["db_exhaustion"])
    elif scenario == "circuit_breaker":
        fail_at_step_idx = rng.randint(1, 4)
        fail_exception = rng.choice(EXCEPTION_CATALOG["circuit_breaker"])
    elif scenario == "business_errors":
        fail_at_step_idx = rng.randint(1, 4)
        fail_exception = rng.choice(EXCEPTION_CATALOG["business_errors"])
    elif scenario in ("realistic", "mixed"):
        roll = rng.random()
        if roll < 0.05:  # 5% slow latency
            slow_step_idx = rng.randint(1, len(wf["steps"]) - 2)
        elif roll < 0.08:  # 3% exception
            fail_at_step_idx = rng.randint(1, len(wf["steps"]) - 2)
            fail_cat = rng.choice(list(EXCEPTION_CATALOG.keys()))
            fail_exception = rng.choice(EXCEPTION_CATALOG[fail_cat])

    # 2. Emisi Transaksi: Step demi Step
    for step_idx, (svc_name, stp_name) in enumerate(wf["steps"]):
        svc_meta = MICROSERVICES[svc_name]
        step_caller = rng.choice(svc_meta["callers"])
        perf_caller = rng.choice(PERF_CALLERS)
        span_caller = rng.choice(SPAN_OPENER_CALLERS)

        # A. Pola C: Opening Span
        lines.append(format_pola_c_span_open(trace_id, svc_name, stp_name, curr_time, span_caller))
        curr_time += timedelta(milliseconds=rng.randint(1, 4))

        # B. Pola B: Emisi Input Variables pada langkah awal / persiapan
        if step_idx == 0:
            for k in var_keys:
                lines.append(format_pola_b_input_var(trace_id, svc_name, k, biz_context[k], curr_time, step_caller))
                curr_time += timedelta(milliseconds=rng.randint(1, 2))

        # C. Pola A: SLA Budget Start
        lines.append(format_pola_a_start(trace_id, svc_name, stp_name, curr_time, caller=perf_caller))
        curr_time += timedelta(milliseconds=rng.randint(1, 3))

        # D. Eksekusi Step (Normal, Slow, atau Error)
        if step_idx == fail_at_step_idx:
            # Step ini GAGAL: Emisi ERROR log
            dur = rng.randint(10, 45)
            curr_time += timedelta(milliseconds=dur)
            err_line = format_pola_d_error(
                trace_id, svc_name, stp_name, fail_exception, curr_time, caller=step_caller
            )
            lines.append(err_line)

            # Pola A End dengan status gagal
            lines.append(format_pola_a_end(trace_id, svc_name, stp_name, dur, curr_time, caller=perf_caller))

            # Transaksi terhenti karena error
            break

        elif step_idx == slow_step_idx:
            # Step ini LAMBAT (> 4000 ms, misal 4200 - 6800 ms)
            dur = rng.randint(4200, 6800)
            curr_time += timedelta(milliseconds=dur)
            lines.append(format_pola_a_end(trace_id, svc_name, stp_name, dur, curr_time, caller=perf_caller))
        else:
            # Step ini NORMAL (sesuai rata-rata durasi microservice)
            min_d, max_d = svc_meta["avg_duration"]
            dur = rng.randint(min_d, max_d)
            curr_time += timedelta(milliseconds=dur)
            lines.append(format_pola_a_end(trace_id, svc_name, stp_name, dur, curr_time, caller=perf_caller))

    return lines, curr_time


def emit_standalone_pola_d(
    trace_id: str,
    rng: random.Random,
    dt_start: datetime,
) -> List[str]:
    """Menghasilkan uncaught exception Java murni tanpa konteks service header"""
    callers = [
        ("com.bank.service.TransactionHandler", "process", 142),
        ("com.bank.service.PaymentProcessor", "executePayment", 88),
        ("database.Connector", "execute", 410),
        ("org.springframework.web.servlet.DispatcherServlet", "doDispatch", 1064),
    ]
    caller = rng.choice(callers)
    all_exceptions = [e for cat in EXCEPTION_CATALOG.values() for e in cat]
    msg = rng.choice(all_exceptions)
    line = format_pola_d_error(trace_id, None, None, msg, dt_start, caller=caller)
    return [line]


# =====================================================================
# 7. CLI PARSER & STREAMING ENGINE
# =====================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enterprise Java Microservice Distributed Tracing Log Generator for ELK Platform",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=[
            "realistic",
            "normal",
            "high_error_rate",
            "repeated_service_error",
            "slow_latency",
            "core_timeout",
            "db_exhaustion",
            "circuit_breaker",
            "business_errors",
            "mixed",
            "pola_d_exception",
        ],
        default="realistic",
        help="Skenario operasional yang disimulasikan",
    )
    parser.add_argument(
        "--workflow",
        choices=list(WORKFLOWS.keys()) + ["random"],
        default="random",
        help="Jenis alur transaksi perbankan yang dijalankan",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Target file log tujuan (terbaca oleh Filebeat)",
    )
    parser.add_argument(
        "--service",
        default=None,
        help="Nama microservice target (untuk skenario repeated_service_error)",
    )
    parser.add_argument(
        "--step",
        default=None,
        help="Nama step microservice target (untuk skenario repeated_service_error)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.4,
        help="Jeda waktu antar transaksi (detik). Jika 0, log dicetak secepat mungkin.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Jumlah transaksi yang dihasilkan (0 = berjalan terus menerus)",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        default=False,
        help="Emisi log baris-per-baris secara real-time dengan jeda mikrodetik antar span",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed integer untuk pengacakan reproduktif",
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

    print("=" * 70)
    print("🚀 ENTERPRISE JAVA MICROSERVICE DISTRIBUTED LOG GENERATOR")
    print("=" * 70)
    print(f"Operational Mode  : {args.mode}")
    print(f"Workflow Scope    : {args.workflow} ({'Randomized' if args.workflow == 'random' else WORKFLOWS[args.workflow]['desc']})")
    print(f"Output Target     : {output_path}")
    print(f"Transaction Gap   : {args.interval}s")
    print(f"Streaming Mode    : {'Line-by-Line Realtime' if args.stream else 'Transaction Block'}")
    print(f"Execution Target  : {'Continuous (Press Ctrl+C to terminate)' if args.count == 0 else f'{args.count} transactions'}")
    print("=" * 70)

    emitted_transactions = 0
    emitted_lines = 0

    with output_path.open("a", encoding="utf-8", buffering=1) as fh:
        while not stop_requested and (args.count == 0 or emitted_transactions < args.count):
            now = datetime.now(JAKARTA_TZ)
            trace_id = generate_trace_id(rng)

            # Pilih workflow
            if args.workflow == "random":
                chosen_wf = rng.choice(list(WORKFLOWS.keys()))
            else:
                chosen_wf = args.workflow

            # Pola D Exception mode
            if args.mode == "pola_d_exception":
                batch = emit_standalone_pola_d(trace_id, rng, now)
            else:
                batch, _ = emit_enterprise_transaction(
                    trace_id=trace_id,
                    workflow_key=chosen_wf,
                    rng=rng,
                    dt_start=now,
                    scenario=args.mode,
                    override_service=args.service,
                    override_step=args.step,
                )

            # Tulis ke file dan console
            for line in batch:
                fh.write(line + "\n")
                print(line)
                emitted_lines += 1
                if args.stream:
                    # Emisi line-by-line realistis (10-35ms antar baris)
                    time.sleep(rng.uniform(0.010, 0.035))

            emitted_transactions += 1

            if args.interval > 0 and (args.count == 0 or emitted_transactions < args.count):
                time.sleep(args.interval)

    print("\n" + "=" * 70)
    print(f"✅ [COMPLETED] Total Transactions: {emitted_transactions} | Total Log Lines: {emitted_lines}")
    print(f"📂 Log file appended: {output_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n🛑 [STOPPED] Generator halted by user signal.")
        sys.exit(0)
