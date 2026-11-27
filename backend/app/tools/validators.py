import fnmatch
import re

from fastapi import HTTPException

from app.config import get_settings

INDEX_RE = re.compile(r"^[a-zA-Z0-9._*?-]+$")


def validate_index_pattern(index_pattern: str) -> str:
    value = index_pattern.strip()

    if not value:
        raise HTTPException(status_code=400, detail="index wajib diisi")

    if value in {"*", "_all"} or "," in value:
        raise HTTPException(
            status_code=400,
            detail="index pattern terlalu luas/tidak diizinkan",
        )

    if not INDEX_RE.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="index pattern mengandung karakter yang tidak diizinkan",
        )

    allowed_patterns = get_settings().elasticsearch_index_allowlist.split(",")
    allowed_patterns = [x.strip() for x in allowed_patterns if x.strip()]

    allowed = any(
        fnmatch.fnmatchcase(value, pattern)
        or fnmatch.fnmatchcase(pattern, value)
        for pattern in allowed_patterns
    )

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"index '{value}' tidak ada dalam allowlist",
        )

    return value


def resolve_search_index(index_pattern: str) -> str:
    """
    Jika index adalah daily index spesifik (contoh: app-logs-2026.09.14),
    arahkan query pencarian Elasticsearch ke pattern wildcard 'app-logs-*'.
    
    Alasan Arsitektur:
    Logstash mempartisi index harian berdasarkan tanggal UTC ('app-logs-%{+YYYY.MM.dd}').
    Karena zona waktu sistem adalah WIB (UTC+7):
    Satu hari penuh tanggal 14 Sep WIB (00:00:00 s/d 23:59:59 WIB) secara fisik tersebar di:
      - 00:00 - 07:00 WIB di index 'app-logs-2026.09.13' (UTC 17:00 - 24:00 kemarin)
      - 07:00 - 24:00 WIB di index 'app-logs-2026.09.14' (UTC 00:00 - 17:00 hari ini)
    Dengan mengarahkan query pencarian ke 'app-logs-*' yang difilter oleh range @timestamp,
    Elasticsearch secara otomatis menarik data 24 jam penuh tanpa terpotong shard UTC,
    persis seperti perilaku Kibana Discover.
    """
    clean = index_pattern.strip()
    match = re.match(r"^([a-zA-Z0-9_-]+)-\d{4}[._-]\d{2}[._-]\d{2}$", clean)
    if match:
        prefix = match.group(1)
        return f"{prefix}-*"
    return clean

def validate_limit(limit: int) -> int:
    max_results = get_settings().tool_max_results
    if limit < 1:
        raise HTTPException(
            status_code=400,
            detail="limit minimal 1"
        )
    if limit > max_results:
        raise HTTPException(
            status_code=400,
            detail=f"limit maksimal {max_results}"
        )
    return limit
