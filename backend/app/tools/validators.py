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
