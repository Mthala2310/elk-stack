from datetime import datetime
from typing import Any

from app.es_client import get_es_client
from app.tools.validators import validate_index_pattern, validate_limit


def _format_caller(ev: dict[str, Any]) -> str | None:
    cls = ev.get("caller_class")
    method = ev.get("caller_method")
    line = ev.get("caller_line")

    if not cls:
        return None
    if method and line is not None:
        return f"{cls}({method}:{line})"
    if method:
        return f"{cls}({method})"
    return str(cls)


def get_trace_timeline(
    trace_id: str,
    index: str = "app-logs-*",
    limit: int = 100,
) -> dict[str, Any]:
    """
    Mengambil dan merekonstruksi seluruh siklus transaksi (distributed trace)
    berdasarkan trace_id secara kronologis.
    """
    if not trace_id or not str(trace_id).strip():
        raise ValueError("trace_id tidak boleh kosong")

    trace_id = str(trace_id).strip()
    index = validate_index_pattern(index)
    limit = validate_limit(limit)

    es = get_es_client()

    # Gunakan exact term matching (hindari 'match' agar tanda minus pada trace_id
    # seperti '-764967383' tidak terhapus oleh analyzer teks)
    query: dict[str, Any] = {
        "bool": {
            "filter": [
                {
                    "bool": {
                        "should": [
                            {"term": {"trace_id.keyword": trace_id}},
                            {"term": {"trace_id": trace_id}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            ]
        }
    }

    result = es.search(
        index=index,
        size=limit,
        track_total_hits=True,
        query=query,
        sort=[
            {"@timestamp": {"order": "asc"}},
        ],
    )

    hits = result["hits"]["hits"]
    total_events = (
        result["hits"]["total"]["value"]
        if isinstance(result["hits"]["total"], dict)
        else result["hits"]["total"]
    )

    if total_events == 0:
        return {
            "trace_id": trace_id,
            "found": False,
            "index": index,
            "total_events": 0,
            "message": (
                f"Tidak ditemukan event log untuk trace_id '{trace_id}' "
                f"pada index '{index}'. (Catatan: Field trace_id hanya tersedia "
                "pada log Microservice Tracing, bukan pada log HTTP akses lama)."
            ),
            "timeline": [],
        }

    events = [hit["_source"] for hit in hits]

    # Ekstraksi metadata & rekonstruksi lifecycle transaksi
    service_name = None
    service_version = None
    input_variables: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    error_logs: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    total_step_duration_ms = 0

    for ev in events:
        if not service_name and ev.get("service_name"):
            service_name = ev.get("service_name")
        if service_version is None and ev.get("service_version") is not None:
            service_version = ev.get("service_version")

        caller = _format_caller(ev)
        level = str(ev.get("log_level", "")).upper()

        # 1. Ekstraksi Input Variables (Pola B Logstash)
        v_name = ev.get("variable_name")
        if v_name:
            input_variables[v_name] = ev.get("variable_value", "")

        # 2. Ekstraksi Step & Latensi Riil (Pola A Logstash, wajib action == "End")
        step = ev.get("step_name")
        dur = ev.get("duration_ms")
        action = ev.get("perf_action")

        if step and action == "End" and dur is not None:
            steps.append({
                "step_name": step,
                "duration_ms": dur,
                "timestamp": ev.get("@timestamp"),
                "caller": caller,
            })
            total_step_duration_ms += dur

        # 3. Deteksi Error & Warning
        if level == "ERROR":
            error_logs.append({
                "timestamp": ev.get("@timestamp"),
                "caller": caller,
                "step_name": step,
                "message": ev.get("message") or ev.get("log_payload"),
            })

        # 4. Susun event timeline yang ringkas (hemat token untuk AI)
        compact_ev: dict[str, Any] = {
            "@timestamp": ev.get("@timestamp"),
            "log_level": ev.get("log_level"),
        }
        if caller:
            compact_ev["caller"] = caller
        if step:
            compact_ev["step_name"] = step
        if action:
            compact_ev["perf_action"] = action
        if action == "End" and dur is not None:
            compact_ev["duration_ms"] = dur
        if v_name:
            compact_ev["variable_name"] = v_name
            if ev.get("variable_value"):
                compact_ev["variable_value"] = ev.get("variable_value")
        if ev.get("log_payload"):
            compact_ev["log_payload"] = ev.get("log_payload")
        if level in ("ERROR", "WARN") or (not step and not v_name and not ev.get("log_payload")):
            if ev.get("message"):
                compact_ev["message"] = ev.get("message")

        timeline.append(compact_ev)

    start_time = events[0].get("@timestamp")
    end_time = events[-1].get("@timestamp")

    # Hitung total waktu wall-clock end-to-end dari event pertama hingga terakhir
    end_to_end_duration_ms = None
    if start_time and end_time:
        try:
            dt_start = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
            dt_end = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
            end_to_end_duration_ms = round((dt_end - dt_start).total_seconds() * 1000)
        except ValueError:
            pass

    # Tentukan status akhir transaksi
    status = "SUCCESS"
    if error_logs:
        status = "FAILED"
    elif not any(ev.get("perf_action") == "End" for ev in events):
        status = "IN_PROGRESS"

    return {
        "trace_id": trace_id,
        "found": True,
        "index": index,
        "service_name": service_name,
        "service_version": service_version,
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "end_to_end_duration_ms": end_to_end_duration_ms,
        "total_step_duration_ms": total_step_duration_ms,
        "total_spans_matched": total_events,
        "spans_returned": len(timeline),
        "truncated": total_events > len(timeline),
        "steps_count": len(steps),
        "steps_executed": steps,
        "input_variables": input_variables,
        "errors": error_logs,
        "timeline": timeline,
    }
