from datetime import datetime
from typing import Any
from app.models import TimeRange

from app.tools.index_info import get_index_info
from app.tools.latest_event import get_latest_event
from app.tools.search_logs import search_logs
from app.tools.log_summary import get_log_summary
from app.tools.top_error_paths import get_top_error_paths
from app.tools.slow_requests import get_slow_requests
from app.tools.error_peak_hours import get_error_peak_hours

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
    if "start" not in arguments:
        raise ValueError("Tool membutuhkan parameter 'start'.")
    
    start_dt = parse_datetime(arguments["start"])
    
    if "end" in arguments:
        end_dt = parse_datetime(arguments["end"])
    else:
        from datetime import timezone
        end_dt = datetime.now(timezone.utc)
        
    return TimeRange(start=start_dt, end=end_dt)

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict:
    if tool_name == "get_index_info":
        return get_index_info(
            index=arguments.get("index", "app-logs-*")
        )
    
    elif tool_name == "get_latest_event":
        return get_latest_event(
            index=arguments.get("index", "app-logs-*")
        )
        
    elif tool_name == "search_logs":
        time_range = build_time_range(arguments)
        return search_logs(
            index=arguments.get("index", "app-logs-*"),
            time_range=time_range,
            status_code=arguments.get("status_code"),
            path=arguments.get("path"),
            keyword=arguments.get("keyword"),
            limit=arguments.get("limit", 20),
            offset=arguments.get("offset", 0)
        )
        
    elif tool_name == "get_log_summary":
        time_range = build_time_range(arguments)
        return get_log_summary(
            index=arguments.get("index", "app-logs-*"),
            time_range=time_range
        )
        
    elif tool_name == "get_top_error_paths":
        time_range = build_time_range(arguments)
        return get_top_error_paths(
            index=arguments.get("index", "app-logs-*"),
            time_range=time_range,
            error_class=arguments.get("error_class", "all"),
            limit=arguments.get("limit", 10)
        )
        
    elif tool_name == "get_slow_requests":
        time_range = build_time_range(arguments)
        return get_slow_requests(
            index=arguments.get("index", "app-logs-*"),
            time_range=time_range,
            min_response_time=arguments.get("min_response_time"),
            limit=arguments.get("limit", 10),
            offset=arguments.get("offset", 0)
        )

    elif tool_name == "get_error_peak_hours":
        # Ubah start dan end menjadi objek TimeRange
        time_range = build_time_range(arguments)
        # Jalankan analisis waktu pada Elasticsearch
        return get_error_peak_hours(
            index=arguments.get("index", "app-logs-*"),
            time_range=time_range,
            category=arguments.get(
                "category", "all_errors"
            ),
            status_code=arguments.get("status_code"),
            path=arguments.get("path"),
            window_hours=arguments.get(
                "window_hours", 1
            ),
        )

    else:
        raise ValueError(f"Tool {tool_name} tidak ditemukan atau tidak didukung.")
