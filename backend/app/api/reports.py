from datetime import datetime, timedelta, timezone
from typing import Literal
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.models import TimeRange
from app.services.report_builder import (
    build_monitoring_report,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/reports",
    tags=["Monitoring Reports"],
)


# =====================================
# 1. REQUEST MODEL
# =====================================

class ReportRequest(BaseModel):
    index: str = "app-logs-*"

    # 15 menit, 1 jam, 24 jam,
    # atau None untuk custom range.
    period_minutes: Literal[
        15, 60, 1440
    ] | None = 60

    start: datetime | None = None
    end: datetime | None = None


# =====================================
# 2. GENERATE REPORT ENDPOINT
# =====================================

@router.post("/generate")
def generate_report(payload: ReportRequest):

    now = datetime.now(timezone.utc)

    # Pilihan durasi otomatis.
    if payload.period_minutes is not None:

        if payload.start is not None or payload.end is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Gunakan period_minutes atau "
                    "custom start/end, bukan keduanya."
                ),
            )

        end = now
        start = end - timedelta(
            minutes=payload.period_minutes
        )

    # Pilihan custom range.
    else:

        if payload.start is None or payload.end is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Custom range membutuhkan start dan end."
                ),
            )

        start = payload.start
        end = payload.end

    # =================================
    # 3. VALIDATE TIME RANGE
    # =================================

    if (
        start.tzinfo is None
        or start.utcoffset() is None
        or end.tzinfo is None
        or end.utcoffset() is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Start dan end wajib memiliki timezone.",
        )

    if end <= start:
        raise HTTPException(
            status_code=422,
            detail="Waktu akhir harus setelah waktu awal.",
        )

    if end - start > timedelta(hours=168):
        raise HTTPException(
            status_code=422,
            detail="Maksimal periode laporan adalah 7 hari.",
        )

    if end > now + timedelta(minutes=1):
        raise HTTPException(
            status_code=422,
            detail="Waktu akhir tidak boleh di masa depan.",
        )

    # =================================
    # 4. BUILD REPORT
    # =================================

    try:
        time_range = TimeRange(
            start=start,
            end=end,
        )

        report = build_monitoring_report(
            index=payload.index,
            time_range=time_range,
        )

        return report

    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        logger.exception(
            "Monitoring report generation failed"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Report gagal dibuat. "
                "Periksa backend dan Elasticsearch."
            ),
        ) from None
