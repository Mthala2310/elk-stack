
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def get_completed_hour(
    now: datetime | None = None,
    timezone_name: str = "Asia/Jakarta",
):
    """
    Mengembalikan periode satu jam kalender
    yang sudah selesai sebelum waktu sekarang.
    """

    zone = ZoneInfo(timezone_name)

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(
            "Waktu harus memiliki timezone."
        )

    local_now = now.astimezone(zone)

    # Contoh: 14:45 menjadi 14:00
    end = local_now.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    # Jam lengkap sebelumnya: 13:00-14:00
    start = end - timedelta(hours=1)

    return start, end


def make_report_window_id(
    index: str,
    start: datetime,
    end: datetime,
) -> str:
    """
    Membuat identitas unik berdasarkan
    index dan periode laporan.
    """

    return (
        f"{index}|"
        f"{start.isoformat()}|"
        f"{end.isoformat()}"
    )
