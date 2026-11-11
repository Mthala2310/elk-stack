import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


# =======================================
# 1. IDENTITAS UNIK INCIDENT
# =======================================

def _incident_key(
    index: str,
    rule_id: str,
    path: str = "",
) -> str:
    raw = f"{index}\0{rule_id}\0{path}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# =======================================
# 2. DATABASE INITIALIZATION
# =======================================

def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_key TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            index_pattern TEXT NOT NULL,
            endpoint TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('OPEN', 'RESOLVED')),
            opened_at TEXT NOT NULL,
            last_observed_at TEXT NOT NULL,
            resolved_at TEXT,
            consecutive_normal INTEGER
                NOT NULL DEFAULT 0,
            evidence_json TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS
            one_open_per_key
        ON incidents(incident_key)
        WHERE status = 'OPEN';

        CREATE TABLE IF NOT EXISTS incident_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL
                REFERENCES incidents(id),
            event_type TEXT NOT NULL
                CHECK (event_type IN ('OPEN', 'RESOLVED')),
            occurred_at TEXT NOT NULL,
            evidence_json TEXT NOT NULL
        );
    """)


# =======================================
# 3. CREATE OR UPDATE OPEN INCIDENT
# =======================================

def _upsert_open(
    conn,
    *,
    index,
    rule_id,
    endpoint,
    evidence,
    now,
    changes,
):
    key = _incident_key(
        index,
        rule_id,
        endpoint or "",
    )

    encoded = json.dumps(
        evidence,
        ensure_ascii=False,
    )

    existing = conn.execute(
        """
        SELECT id FROM incidents
        WHERE incident_key = ?
          AND status = 'OPEN'
        """,
        (key,),
    ).fetchone()

    # Incident sudah OPEN.
    # Perbarui evidence, jangan membuat duplikat.
    if existing:
        conn.execute(
            """
            UPDATE incidents
            SET last_observed_at = ?,
                consecutive_normal = 0,
                evidence_json = ?
            WHERE id = ?
            """,
            (now, encoded, existing["id"]),
        )

        return

    # Incident belum OPEN, buat record baru.
    cursor = conn.execute(
        """
        INSERT INTO incidents (
            incident_key,
            rule_id,
            index_pattern,
            endpoint,
            status,
            opened_at,
            last_observed_at,
            evidence_json
        )
        VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?)
        """,
        (
            key,
            rule_id,
            index,
            endpoint,
            now,
            now,
            encoded,
        ),
    )

    incident_id = cursor.lastrowid

    # Catat transisi pertama pada history.
    conn.execute(
        """
        INSERT INTO incident_events (
            incident_id,
            event_type,
            occurred_at,
            evidence_json
        )
        VALUES (?, 'OPEN', ?, ?)
        """,
        (incident_id, now, encoded),
    )

    changes.append({
        "incident_id": incident_id,
        "event": "OPEN",
        "rule_id": rule_id,
        "endpoint": endpoint,
    })


# =======================================
# 4. CONFIRM INCIDENT RECOVERY
# =======================================

def _confirm_normal(
    conn,
    *,
    index,
    rule_id,
    active_keys,
    confirmations,
    now,
    changes,
):
    rows = conn.execute(
        """
        SELECT id,
               incident_key,
               consecutive_normal,
               evidence_json,
               endpoint
        FROM incidents
        WHERE index_pattern = ?
          AND rule_id = ?
          AND status = 'OPEN'
        """,
        (index, rule_id),
    ).fetchall()

    for row in rows:
        # Jika rule/path masih terpicu,
        # jangan proses sebagai NORMAL.
        if row["incident_key"] in active_keys:
            continue

        consecutive = (
            row["consecutive_normal"] + 1
        )

        # Belum cukup konfirmasi pemulihan.
        if consecutive < confirmations:
            conn.execute(
                """
                UPDATE incidents
                SET consecutive_normal = ?
                WHERE id = ?
                """,
                (consecutive, row["id"]),
            )

            continue

        # Pemulihan sudah terkonfirmasi.
        conn.execute(
            """
            UPDATE incidents
            SET status = 'RESOLVED',
                resolved_at = ?,
                consecutive_normal = ?
            WHERE id = ?
            """,
            (now, consecutive, row["id"]),
        )

        # Simpan event RESOLVED.
        conn.execute(
            """
            INSERT INTO incident_events (
                incident_id,
                event_type,
                occurred_at,
                evidence_json
            )
            VALUES (?, 'RESOLVED', ?, ?)
            """,
            (
                row["id"],
                now,
                row["evidence_json"],
            ),
        )

        changes.append({
            "incident_id": row["id"],
            "event": "RESOLVED",
            "rule_id": rule_id,
            "endpoint": row["endpoint"],
        })


# =======================================
# 5. RESET RECOVERY CONFIRMATION
# =======================================

def _reset_confirmation(
    conn,
    *,
    index,
    rule_id,
):
    # Jika evaluasi tidak meyakinkan,
    # hentikan progres menuju RESOLVED.
    conn.execute(
        """
        UPDATE incidents
        SET consecutive_normal = 0
        WHERE index_pattern = ?
          AND rule_id = ?
          AND status = 'OPEN'
        """,
        (index, rule_id),
    )


# =======================================
# 6. INCIDENT LIFECYCLE ORCHESTRATION
# =======================================

def apply_incident_lifecycle(
    evaluation: dict,
    db_path: str | Path,
    confirmations: int = 2,
    now: datetime | None = None,
) -> list[dict]:
    if (
        isinstance(confirmations, bool)
        or not isinstance(confirmations, int)
        or confirmations < 1
    ):
        raise ValueError(
            "confirmations harus integer >= 1"
        )

    timestamp = (
        now or datetime.now(WIB)
    ).astimezone(WIB).isoformat()

    db_path = Path(db_path)

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    changes = []
    index = evaluation["index"]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        for rule in evaluation["rules"]:
            rule_id = rule["rule_id"]
            status = rule["status"]

            # ---------------------------
            # HIGH 4XX & HIGH 5XX
            # ---------------------------

            if rule_id in {
                "HIGH_4XX_ERROR_RATE",
                "HIGH_5XX_ERROR_RATE",
            }:
                if status == "TRIGGERED":
                    evidence = {
                        "window_start": evaluation[
                            "window_start"
                        ],
                        "window_end": evaluation[
                            "window_end"
                        ],
                        "total_events": rule[
                            "total_events"
                        ],
                        "error_count": rule[
                            "error_count"
                        ],
                        "error_rate_percent": rule[
                            "error_rate_percent"
                        ],
                        "threshold": rule[
                            "threshold"
                        ],
                    }

                    _upsert_open(
                        conn,
                        index=index,
                        rule_id=rule_id,
                        endpoint=None,
                        evidence=evidence,
                        now=timestamp,
                        changes=changes,
                    )

                elif status == "NORMAL":
                    _confirm_normal(
                        conn,
                        index=index,
                        rule_id=rule_id,
                        active_keys=set(),
                        confirmations=confirmations,
                        now=timestamp,
                        changes=changes,
                    )

                else:
                    # NO_DATA / LOW_TRAFFIC /
                    # evaluasi tidak meyakinkan.
                    _reset_confirmation(
                        conn,
                        index=index,
                        rule_id=rule_id,
                    )

            # ---------------------------
            # REPEATED ERROR ENDPOINT
            # ---------------------------

            elif rule_id == "REPEATED_ERROR_ENDPOINT":
                active_keys = set()

                if status == "TRIGGERED":
                    for item in rule[
                        "triggered_endpoints"
                    ]:
                        path = item["path"]

                        key = _incident_key(
                            index,
                            rule_id,
                            path,
                        )

                        active_keys.add(key)

                        evidence = {
                            "window_start": evaluation[
                                "window_start"
                            ],
                            "window_end": evaluation[
                                "window_end"
                            ],
                            "error_count": item[
                                "error_count"
                            ],
                            "status_counts": item[
                                "status_counts"
                            ],
                            "threshold": rule[
                                "threshold"
                            ],
                        }

                        _upsert_open(
                            conn,
                            index=index,
                            rule_id=rule_id,
                            endpoint=path,
                            evidence=evidence,
                            now=timestamp,
                            changes=changes,
                        )

                # Hanya proses pemulihan bila
                # hasil agregasi lengkap.
                if (
                    status in {"TRIGGERED", "NORMAL"}
                    and not rule["coverage_partial"]
                ):
                    _confirm_normal(
                        conn,
                        index=index,
                        rule_id=rule_id,
                        active_keys=active_keys,
                        confirmations=confirmations,
                        now=timestamp,
                        changes=changes,
                    )

                else:
                    _reset_confirmation(
                        conn,
                        index=index,
                        rule_id=rule_id,
                    )

            # ---------------------------
            # STALE / NO LOG
            # ---------------------------

            elif rule_id == "STALE_NO_LOG":
                if status == "TRIGGERED":
                    evidence = {
                        "window_end": evaluation["window_end"],
                        "reason": rule["reason"],
                        "last_event_at": rule["last_event_at"],
                        "age_seconds": rule["age_seconds"],
                        "threshold_seconds": rule[
                            "threshold_seconds"
                        ],
                    }

                    _upsert_open(
                        conn,
                        index=index,
                        rule_id=rule_id,
                        endpoint=None,
                        evidence=evidence,
                        now=timestamp,
                        changes=changes,
                    )

                elif status == "NORMAL":
                    _confirm_normal(
                        conn,
                        index=index,
                        rule_id=rule_id,
                        active_keys=set(),
                        confirmations=confirmations,
                        now=timestamp,
                        changes=changes,
                    )

                else:
                    # DISABLED / WARMING_UP / UNKNOWN
                    # Tidak boleh dianggap pulih.
                    _reset_confirmation(
                        conn,
                        index=index,
                        rule_id=rule_id,
                    )

            # ---------------------------
            # HIGH RESPONSE TIME
            # ---------------------------
            elif rule_id == "HIGH_RESPONSE_TIME":
                if status == "TRIGGERED":
                    evidence = {
                        "window_start": evaluation[
                            "window_start"
                        ],
                        "window_end": evaluation[
                            "window_end"
                        ],
                        "sample_count": rule[
                            "sample_count"
                        ],
                        "p95_ms": rule["p95_ms"],
                        "slow_request_count": rule[
                            "slow_request_count"
                        ],
                        "slow_request_rate_percent": rule[
                            "slow_request_rate_percent"
                        ],
                        "threshold": rule["threshold"],
                        "unit": "ms",
                    }

                    _upsert_open(
                        conn,
                        index=index,
                        rule_id=rule_id,
                        endpoint=None,
                        evidence=evidence,
                        now=timestamp,
                        changes=changes,
                    )

                elif status == "NORMAL":
                    _confirm_normal(
                        conn,
                        index=index,
                        rule_id=rule_id,
                        active_keys=set(),
                        confirmations=confirmations,
                        now=timestamp,
                        changes=changes,
                    )

                else:
                    # NO_LATENCY_DATA / LOW_SAMPLE / UNKNOWN
                    # Tidak boleh dianggap pulih.
                    _reset_confirmation(
                        conn,
                        index=index,
                        rule_id=rule_id,
                    )

    return changes


# =======================================
# 7. READ INCIDENT HISTORY
# =======================================

def list_incidents(
    db_path: str | Path,
    limit: int = 10,
) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError(
            "limit harus antara 1-100"
        )

    db_path = Path(db_path)

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _init_db(conn)

        rows = conn.execute(
            """
            SELECT id,
                   rule_id,
                   index_pattern,
                   endpoint,
                   status,
                   opened_at,
                   last_observed_at,
                   resolved_at,
                   consecutive_normal,
                   evidence_json
            FROM incidents
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        items = []

        for row in rows:
            item = dict(row)

            item["evidence"] = json.loads(
                item.pop("evidence_json")
            )

            items.append(item)

        return items
