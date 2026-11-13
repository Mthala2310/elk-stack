from datetime import datetime, timezone
from typing import Any
from app.models import TimeRange

from app.tools.index_info import get_index_info
from app.tools.latest_event import get_latest_event
from app.tools.search_logs import search_logs
from app.tools.log_summary import get_log_summary
from app.tools.top_error_paths import get_top_error_paths
from app.tools.slow_requests import get_slow_requests
from app.tools.error_peak_hours import get_error_peak_hours
from app.tools.trace_lookup import get_trace_timeline


def _opt(arguments: dict[str, Any], key: str, default: Any) -> Any:
    """Mengambil nilai opsional dengan aman walau LLM mengirim JSON null."""
    val = arguments.get(key)
    return default if val is None else val


def parse_datetime(value: str) -> datetime:
    try:
        # Supaya format ...Z aman dibaca Python
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Format datetime tidak valid: {value}"
        ) from exc


def build_time_range(arguments: dict[str, Any]) -> TimeRange:
    raw_start = arguments.get("start")
    if not raw_start:
        raise ValueError("Tool membutuhkan parameter 'start'.")

    start_dt = parse_datetime(str(raw_start))

    raw_end = arguments.get("end")
    if raw_end:
        end_dt = parse_datetime(str(raw_end))
    else:
        end_dt = datetime.now(timezone.utc)

    return TimeRange(start=start_dt, end=end_dt)


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    index = str(_opt(arguments, "index", "app-logs-*"))

    if tool_name == "get_index_info":
        return get_index_info(index=index)

    elif tool_name == "get_latest_event":
        return get_latest_event(index=index)

    elif tool_name == "search_logs":
        time_range = build_time_range(arguments)
        raw_trace = arguments.get("trace_id")
        return search_logs(
            index=index,
            time_range=time_range,
            status_code=arguments.get("status_code"),
            path=arguments.get("path"),
            keyword=arguments.get("keyword"),
            trace_id=str(raw_trace) if raw_trace is not None else None,
            service_name=arguments.get("service_name"),
            step_name=arguments.get("step_name"),
            log_level=arguments.get("log_level"),
            limit=_opt(arguments, "limit", 20),
            offset=_opt(arguments, "offset", 0),
        )

    elif tool_name == "trace_lookup":
        raw_trace = arguments.get("trace_id")
        if raw_trace is None or not str(raw_trace).strip():
            raise ValueError("Tool 'trace_lookup' membutuhkan parameter 'trace_id'.")
        return get_trace_timeline(
            trace_id=str(raw_trace).strip(),
            index=index,
            limit=_opt(arguments, "limit", 100),
        )

    elif tool_name == "get_log_summary":
        time_range = build_time_range(arguments)
        return get_log_summary(
            index=index,
            time_range=time_range,
        )

    elif tool_name == "get_top_error_paths":
        time_range = build_time_range(arguments)
        return get_top_error_paths(
            index=index,
            time_range=time_range,
            error_class=_opt(arguments, "error_class", "all"),
            limit=_opt(arguments, "limit", 10),
        )

    elif tool_name == "get_slow_requests":
        time_range = build_time_range(arguments)
        return get_slow_requests(
            index=index,
            time_range=time_range,
            min_response_time=arguments.get("min_response_time"),
            limit=_opt(arguments, "limit", 10),
            offset=_opt(arguments, "offset", 0),
        )

    elif tool_name == "get_error_peak_hours":
        time_range = build_time_range(arguments)
        return get_error_peak_hours(
            index=index,
            time_range=time_range,
            category=_opt(arguments, "category", "all_errors"),
            status_code=arguments.get("status_code"),
            path=arguments.get("path"),
            service_name=arguments.get("service_name"),
            window_hours=_opt(arguments, "window_hours", 1),
        )

    else:
        raise ValueError(f"Tool {tool_name} tidak ditemukan atau tidak didukung.")
