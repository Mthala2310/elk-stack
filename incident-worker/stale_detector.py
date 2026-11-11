from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def get_latest_log_timestamp(es, index: str):
    """
    Cari timestamp event terbaru di Elasticsearch.
    Hanya mengambil @timestamp, bukan raw log.
    """

    result = es.search(
        index=index,
        size=1,
        track_total_hits=False,
        query={
            "exists": {
                "field": "@timestamp"
            }
        },
        sort=[
            {"@timestamp": {"order": "desc"}}
        ],
        source=["@timestamp"],
    )

    hits = result["hits"]["hits"]

    if not hits:
        return None

    value = hits[0].get(
        "_source", {}
    ).get("@timestamp")

    if not value:
        raise ValueError(
            "Event ditemukan tetapi @timestamp "
            "tidak tersedia pada _source."
        )

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(WIB)


def evaluate_stale_rule(
    *,
    expected_active: bool,
    latest_event_at: datetime | None,
    now: datetime,
    worker_started_at: datetime,
    stale_after_seconds: int = 600,
    startup_grace_seconds: int = 600,
) -> dict:
    """
    Evaluasi apakah log sudah terlalu lama
    tidak diperbarui.
    """

    if stale_after_seconds < 1:
        raise ValueError(
            "stale_after_seconds harus >= 1."
        )

    if startup_grace_seconds < 0:
        raise ValueError(
            "startup_grace_seconds tidak boleh negatif."
        )

    for name, value in (
        ("now", now),
        ("worker_started_at", worker_started_at),
        ("latest_event_at", latest_event_at),
    ):
        if value is not None and (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{name} wajib memiliki timezone."
            )

    status = "UNKNOWN"
    reason = "UNDETERMINED"
    age_seconds = None

    if not expected_active:
        status = "DISABLED"
        reason = "SOURCE_NOT_EXPECTED_ACTIVE"

    elif latest_event_at is None:

        uptime = (
            now - worker_started_at
        ).total_seconds()

        if uptime < 0:
            raise ValueError(
                "now tidak boleh sebelum worker_started_at."
            )

        if uptime < startup_grace_seconds:
            status = "WARMING_UP"
            reason = "WAITING_FOR_FIRST_EVENT"
        else:
            status = "TRIGGERED"
            reason = "NO_EVENTS_FOUND"

    else:
        age_seconds = (
            now - latest_event_at
        ).total_seconds()

        if age_seconds < -60:
            status = "UNKNOWN"
            reason = "FUTURE_EVENT_TIMESTAMP"

        elif age_seconds > stale_after_seconds:
            status = "TRIGGERED"
            reason = "LAST_EVENT_TOO_OLD"

        else:
            status = "NORMAL"
            reason = "LOG_FRESH"

    return {
        "rule_id": "STALE_NO_LOG",
        "status": status,
        "reason": reason,
        "expected_active": expected_active,

        "last_event_at": (
            latest_event_at.isoformat()
            if latest_event_at
            else None
        ),

        "age_seconds": (
            round(age_seconds, 2)
            if age_seconds is not None
            else None
        ),

        "threshold_seconds": stale_after_seconds,
    }
