# Phase 5 - Step 1

## Goal
Bootstrap FastAPI, connect to Elasticsearch, add index allowlist, and implement the first read-only tool: `get_index_info()`.

## Root project `.env`
Add:

```env
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX_ALLOWLIST=app-logs-*
TOOL_MAX_RESULTS=100
TOOL_MAX_LOOKBACK_HOURS=168
```

## Install
From `~/elk-stack/backend`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Test

```bash
curl http://localhost:8000/api/system/health
curl 'http://localhost:8000/api/tools/index-info?index=app-logs-*'
```

Swagger:
`http://localhost:8000/docs`
