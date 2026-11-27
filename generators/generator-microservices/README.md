# Enterprise Java Microservice Distributed Log Generator

Generator log sintetis skala industri untuk menyimulasikan sistem perbankan/fintech terdistribusi riil dengan distributed tracing, multiple collaborating microservices, variasi parameter bisnis perbankan, dan skenario kegagalan operasional.

## 🏛️ Topologi Layanan (Microservices Catalog)

| Microservice | Version | Peran & Domain Bisnis | Caller Package |
|---|---|---|---|
| `authService` | Ver. 4 | OAuth2 token validation, IAM session | `com.bank.gateway.auth` |
| `accountInquiryService` | Ver. 3 | Balance check, CIF portfolio lookup, hold balances | `com.bank.account.service` |
| `beneficiaryValidationService` | Ver. 7 | BI-FAST proxy routing, central bank clearing | `com.bank.payment.bifast` |
| `fraudDetectionEngine` | Ver. 1 | Velocity scoring, AML sanction blacklist, device trust | `com.bank.fraud.engine` |
| `fundTransferCoreService` | Ver. 5 | Ledger balance reservation, core host debit/credit | `com.bank.core.ledger` |
| `paymentGatewayService` | Ver. 2 | QRIS dynamic parsing, NMID merchant acquirer | `com.bank.payment.qris` |
| `vaManagementService` | Ver. 2 | Virtual account billing validation & biller webhooks | `com.bank.va.billing` |
| `notificationDispatcher` | Ver. 2 | Real-time push notification, SMTP receipt delivery | `com.bank.notification` |
| `auditComplianceService` | Ver. 1 | Immutable ledger audit journal & compliance records | `com.bank.audit.compliance` |

---

## 🔄 Alur Transaksi Perbankan Terdistribusi (`--workflow`)

Setiap transaksi membagikan satu `trace_id` yang sama melintasi span hierarkis antar-microservice:

1. **`BI_FAST_TRANSFER`**: Transfer dana antar bank via Bank Indonesia FAST.
   `authService` &rarr; `accountInquiryService` &rarr; `beneficiaryValidationService` &rarr; `fraudDetectionEngine` &rarr; `fundTransferCoreService` &rarr; `notificationDispatcher` &rarr; `auditComplianceService`.
2. **`QRIS_PAYMENT`**: Pembayaran merchant QRIS dinamis/statis.
   `authService` &rarr; `paymentGatewayService` &rarr; `accountInquiryService` &rarr; `fraudDetectionEngine` &rarr; `fundTransferCoreService` &rarr; `notificationDispatcher` &rarr; `auditComplianceService`.
3. **`VIRTUAL_ACCOUNT_PAYMENT`**: Pembayaran instan Virtual Account e-commerce & billing.
   `vaManagementService` &rarr; `accountInquiryService` &rarr; `fundTransferCoreService` &rarr; `vaManagementService` &rarr; `notificationDispatcher` &rarr; `auditComplianceService`.
4. **`ACCOUNT_STATEMENT_INQUIRY`**: Pengecekan saldo, mutasi, dan portofolio nasabah.
   `authService` &rarr; `accountInquiryService` &rarr; `auditComplianceService`.
5. **`BATCH_PAYROLL_DISBURSEMENT`**: Penggajian massal multi-rekening korporasi.
   `authService` &rarr; `accountInquiryService` &rarr; `fundTransferCoreService` &rarr; `notificationDispatcher` &rarr; `auditComplianceService`.

---

## 🛠️ Pilihan Skenario Operasional (`--mode`)

- **`realistic`** *(Default)*: Lalu lintas perbankan normal (92% sukses), degradasi latensi sesekali (5% step lambat > 4000ms), dan anomali/exception perbankan (3%).
- **`normal`**: 100% transaksi sukses cepat (durasi 5 - 150 ms).
- **`high_error_rate`**: Gelombang error mendadak (>15%) untuk menguji trigger rule `HIGH_ERROR_LOG_RATE`.
- **`repeated_service_error`**: Rentetan error berulang pada microservice dan step spesifik untuk menguji trigger rule `REPEATED_ERROR_ENDPOINT`.
- **`slow_latency`**: P95 response time step lambat (>4000 ms, misal 4200 - 6800 ms) untuk menguji trigger rule `HIGH_RESPONSE_TIME`.
- **`core_timeout`**: Simulasi timeout koneksi ke Core Banking Host (`SocketTimeoutException` ke port 9000).
- **`db_exhaustion`**: Simulasi kehabisan pool koneksi basis data (`HikariPool-Core Connection is not available`).
- **`circuit_breaker`**: Simulasi trip Circuit Breaker Resilience4j (`CircuitBreakerOpenException`).
- **`business_errors`**: Simulasi validasi bisnis gagal (`InsufficientFundsException`, `BeneficiaryAccountNotFoundException`).

---

## 💻 Cara Menjalankan

Jalankan script generator dari WSL atau root direktori project:

```bash
# 1. Menjalankan skenario realistis skala industri (5 transaksi):
python3 generators/generator-microservices/log_generator.py --count 5 --mode realistic

# 2. Menjalankan skenario secara real-time streaming baris per baris:
python3 generators/generator-microservices/log_generator.py --count 10 --stream --interval 0.5

# 3. Menjalankan skenario kegagalan Core Banking Host:
python3 generators/generator-microservices/log_generator.py --count 10 --mode core_timeout

# 4. Menjalankan skenario kehabisan database pool HikariCP:
python3 generators/generator-microservices/log_generator.py --count 10 --mode db_exhaustion

# 5. Menguji repeated error pada service tertentu:
python3 generators/generator-microservices/log_generator.py --count 15 --mode repeated_service_error --service "beneficiaryValidationService Ver. 7" --step "routingLookup"

# 6. Menjalankan terus-menerus (continuous stream) dengan jeda 0.3 detik:
python3 generators/generator-microservices/log_generator.py --interval 0.3 --stream
# (Tekan Ctrl+C untuk menghentikan)

# Atau menggunakan alias runner worker.py:
python3 generators/generator-microservices/worker.py --mode realistic --count 5
```
