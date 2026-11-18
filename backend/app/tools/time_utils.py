from datetime import datetime, timezone, timedelta
from typing import Any

try:
    from zoneinfo import ZoneInfo
    JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    JAKARTA_TZ = timezone(timedelta(hours=7))


def to_wib_iso(ts: Any) -> str | None:
    """
    Mengonversi string timestamp ISO UTC (contoh: '2026-10-15T15:55:34.874Z')
    menjadi ISO string dengan timezone WIB (+07:00), contoh: '2026-10-15T22:55:34.874+07:00'.
    """
    if not ts or not isinstance(ts, str):
        return ts
    try:
        clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JAKARTA_TZ).isoformat()
    except Exception:
        return ts


def to_wib_str(ts: Any) -> str | None:
    """
    Mengonversi string timestamp ISO UTC menjadi string ramah manusia
    berzona waktu WIB, contoh: '2026-10-15 22:55:34 WIB'.
    """
    if not ts or not isinstance(ts, str):
        return ts
    try:
        clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S WIB")
    except Exception:
        return ts
