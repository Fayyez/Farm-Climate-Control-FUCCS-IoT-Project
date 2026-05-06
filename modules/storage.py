from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

from modules.processing import SensorSnapshot, snapshot_to_csv_row

log = logging.getLogger(__name__)

CSV_FIELDS = [
    "timestamp_iso",
    "temperature",
    "humidity",
    "smoke_level",
    "smoke_category",
    "window_open",
    "cooling_on",
]

MAX_RECORDS = 1000


def ensure_csv_with_header(csv_path: str) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


def append_snapshot(csv_path: str, snapshot: SensorSnapshot) -> None:
    """Append one reading and trim file to the last MAX_RECORDS data rows."""
    ensure_csv_with_header(csv_path)
    row = snapshot_to_csv_row(snapshot)
    path = Path(csv_path)

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        if set(fields) != set(CSV_FIELDS):
            log.warning("CSV schema mismatch at %s; resetting stored history", csv_path)
            existing: list[dict[str, str]] = []
        else:
            existing = [{k: r.get(k, "") for k in CSV_FIELDS} for r in reader]

    existing.append({k: row.get(k, "") for k in CSV_FIELDS})
    trimmed = False
    if len(existing) > MAX_RECORDS:
        existing = existing[-MAX_RECORDS:]
        trimmed = True

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(existing)

    log.debug(
        "csv write rows=%s cap=%s trimmed=%s path=%s",
        len(existing),
        MAX_RECORDS,
        trimmed,
        csv_path,
    )


def count_records(csv_path: str) -> int:
    if not os.path.exists(csv_path):
        return 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        return max(0, sum(1 for _ in csv.DictReader(f)))
