# AI-Enhanced Centralized Log Monitoring and Incident Analysis Platform

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Elasticsearch 9.5](https://img.shields.io/badge/Elasticsearch-9.5.3-005571?style=flat&logo=elasticsearch&logoColor=white)](https://www.elastic.co/)
[![Kibana 9.5](https://img.shields.io/badge/Kibana-9.5.3-E5007E?style=flat&logo=kibana&logoColor=white)](https://www.elastic.co/kibana)
[![Redis](https://img.shields.io/badge/Redis-7.4--alpine-DC382D?style=flat&logo=redis&logoColor=white)](https://redis.io/)
[![OpenRouter AI](https://img.shields.io/badge/AI%20Copilot-OpenRouter%20API-6366F1?style=flat&logo=openai&logoColor=white)](https://openrouter.ai/)
[![Vite](https://img.shields.io/badge/Frontend-Vite%20SPA-646CFF?style=flat&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Docker](https://img.shields.io/badge/Docker%20Compose-Orchestrated-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)

Platform pemantauan log terpusat, analisis insiden otomatis, pelaporan berkala, dan asisten investigasi berbasis AI yang mendukung pemantauan **HTTP Access Log** maupun **Application / Microservice Log**.

## Ringkasan Proyek

Proyek ini dirancang untuk membantu tim teknis dan operasional memantau kesehatan sistem secara terpusat, melakukan investigasi berbasis bukti data (*evidence*) dari Elasticsearch, mendeteksi serta menotifikasi insiden secara otomatis, dan menghasilkan laporan monitoring tanpa perlu menarik seluruh isi indeks secara manual.

Pengembangan platform dilakukan secara bertahap mulai akhir September 2026:
1. **Fondasi & Pipeline ELK:** Penyusunan PRD, perancangan arsitektur *Project Hub*, konfigurasi lingkungan Docker, serta penstabilan aliran data dari log generator ke **Filebeat → Redis → Logstash → Elasticsearch** dan **Kibana**.
2. **Backend FastAPI & AI Copilot:** Pengembangan layanan backend berbasis Python & FastAPI dengan *observability tools* terarah, *System Prompt*, dan *Tool Definitions* untuk *tool calling* ke Elasticsearch.
3. **Deteksi Insiden, Notifikasi & Pelaporan:** Pengembangan *Incident Worker* berbasis SQLite, *Notification Worker* ke Telegram, *Report Builder*, *Manual Report*, *Scheduled Report Worker* per jam, serta pengambilan *screenshot* dashboard Kibana menggunakan Playwright.
4. **Adaptasi Application / Microservice Log:** Penyesuaian *parser* Grok multi-kategori, *tools hybrid* lintas skema, penelusuran berbasis `Trace ID`, penyesuaian *worker* & notifikasi, serta *adaptive report viewer* di sisi *frontend*.

## Arsitektur & Komponen Utama

- **Log Ingestion & Storage (`Filebeat`, `Redis`, `Logstash`, `Elasticsearch`, `Kibana`):**
  - Mengumpulkan log dari generator/sumber aplikasi melalui Filebeat, menyangga aliran data menggunakan Redis, memproses dan mem-parsing log di Logstash, menyimpan ke Elasticsearch, serta memvisualisasikannya di Kibana.
  - Menggunakan pola parsing **Grok multi-kategori** untuk log aplikasi/microservice (mencakup metrik performa, parameter bisnis, *trace*, dan aturan *fallback* untuk log di luar pola utama).
- **Backend & AI Copilot (`Python`, `FastAPI`):**
  - Menyediakan *observability tools* terarah (ringkasan log, pencarian log, *top error endpoints*, *slow requests*, dan *latest events*) agar AI mengambil data relevan secara efisien.
  - Menyediakan **tools hybrid** lintas skema dan **trace lookup** berdasarkan `Trace ID` untuk menelusuri keterkaitan log di berbagai skema/format.
  - Mengintegrasikan *System Prompt* dan *Tool Definitions* agar AI Copilot menyajikan analisis yang akurat berdasarkan data Elasticsearch.
- **Incident Detection & State Management (`Incident Worker`, `SQLite`):**
  - Mendeteksi kondisi abnormal seperti error HTTP, pengulangan error pada *endpoint*, latensi tinggi, serta absennya log dalam periode tertentu.
  - Mencatat insiden berstatus `OPEN` pada SQLite dan memperbaruinya menjadi `RESOLVED` setelah memenuhi mekanisme konfirmasi pemulihan.
- **Alerting & Reporting (`Notification Worker`, `Report Builder`, `Scheduled Report Worker`, `Playwright`, `Telegram`):**
  - Mengirimkan notifikasi insiden (`OPEN` dan `RESOLVED`) ke Telegram dengan mekanisme pencegahan pengiriman berulang untuk *event* yang sama.
  - Menyusun ringkasan metrik melalui *Report Builder* (jumlah *event*/*request*, distribusi status, *error rate*, *top error endpoint*, *slow requests*, *data freshness*, serta metrik microservice).
  - Mendukung pembuatan laporan manual per indeks & rentang waktu serta laporan terjadwal setiap jam (menggunakan jendela satu jam penuh sebelumnya), lengkap dengan *screenshot* dashboard Kibana via Playwright.
- **Frontend & Adaptive Report Viewer:**
  - Menyediakan antarmuka pemantauan, panel *Manual Report*, dan *adaptive report viewer* yang menyesuaikan label serta *badge* secara otomatis—menampilkan status HTTP untuk *access log* atau level log (`DEBUG`, `INFO`, `WARN`, `ERROR`) untuk *microservice log*.

## Tech Stack

- **Backend & AI Integration:** Python, FastAPI, AI Tool Calling
- **Log Pipeline & Observability:** Elasticsearch, Logstash, Filebeat, Redis, Kibana
- **State & Automation:** SQLite, Background Workers (Incident, Notification, Scheduled Report)
- **Reporting & Visualization:** Playwright, Telegram Bot API, Adaptive Report Viewer
- **Infrastructure:** Docker

## Pengujian & Pemisahan Tanggung Jawab

Pengujian integrasi dilakukan pada keterhubungan *frontend*, *backend*, *Incident Worker*, *Notification Worker*, dan *Report Worker*, termasuk skenario kemunculan error baru serta *troubleshooting* koneksi antarkomponen. Arsitektur ini menerapkan pemisahan tanggung jawab (*separation of concerns*) antara pengumpulan log, deteksi insiden, pengiriman notifikasi, dan pembuatan laporan agar kendala pada satu bagian tidak menghentikan keseluruhan alur kerja secara langsung.

### 1. Menjalankan Infrastruktur Docker (ELK Cluster + Redis)
```bash
# Pastikan Docker Desktop / daemon aktif
docker compose up -d elasticsearch redis logstash kibana filebeat
```
Verifikasi port layanan:
- **Elasticsearch**: `http://localhost:9200`
- **Kibana Web UI**: `http://localhost:5601`
- **Logstash API**: `http://localhost:9600`
- **Redis CLI**: `localhost:6379`

### 2. Menjalankan FastAPI Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Jalankan server API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Akses Swagger UI API: `http://localhost:8000/docs`

### 3. Menjalankan Frontend Workspace SPA
```bash
cd workspace
npm install
npm run dev -- --host
```
Akses Workspace Portal: `http://localhost:5173`

### 4. Menjalankan Background Automation Workers
Buka terminal terpisah untuk masing-masing worker:

```bash
# A. Incident Detection Worker (Mengevaluasi anomali tiap 60s)
cd incident-worker
python3 worker.py

# B. Notification Worker (Mendistribusikan alert ke Telegram tiap 10s)
cd notification-worker
python3 worker.py

# (Opsional) Memaksa pengiriman ulang antrean UNCERTAIN yang tertahan:
python3 worker.py --retry-uncertain --once

# C. Report Worker (Menjadwalkan laporan eksekutif berkala)
cd report-worker
python3 scheduler.py
```

### 5. Menjalankan Log Generator (Simulasi Lalu Lintas Data)

```bash
# A. Generator Log Microservices Skala Industri (9 Services, 5 Workflows)
cd generators/generator-microservices

# Simulasi realistis (92% normal, 5% slow, 3% exceptions):
python3 log_generator.py --count 10 --mode realistic

# Simulasi streaming real-time baris-per-baris:
python3 log_generator.py --stream --interval 0.5

# Simulasi skenario insiden (Core banking timeout / High Error Rate):
python3 log_generator.py --count 15 --mode core_timeout
python3 log_generator.py --count 15 --mode high_error_rate

# B. Generator Log HTTP Web Access
cd generators/generator-http
python3 generator_endPoint.py
```

---