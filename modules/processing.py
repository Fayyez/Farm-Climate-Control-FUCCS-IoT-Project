from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _to_bool(val: Any) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(int(val))
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("1", "true", "on", "yes", "open"):
            return True
        if s in ("0", "false", "off", "no", "closed", "close"):
            return False
    return None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def categorize_smoke_level(smoke_level: float | None) -> str | None:
    """
    MQ-2 smoke_level is expected in 0–4035 range from firmware.

    Clean Air: 0–500, Moderate: 500–1200, Heavy: 1200+
    Boundaries: [0,500) clean, [500,1200) moderate, [1200,∞) heavy.
    """
    if smoke_level is None:
        return None
    if smoke_level < 500:
        return "Clean Air"
    if smoke_level < 1200:
        return "Moderate"
    return "Heavy"


@dataclass
class SensorSnapshot:
    timestamp_iso: str
    temperature: float | None
    humidity: float | None
    smoke_level: float | None
    smoke_category: str | None
    window_open: bool | None
    cooling_on: bool | None
    particle_ok: bool
    error_message: str | None = None


def build_snapshot(raw: dict[str, Any | None], *, particle_configured: bool) -> SensorSnapshot:
    """Normalize Particle variable dict into a dashboard/storage snapshot."""
    now = datetime.now(timezone.utc).isoformat()
    temp = _to_float(raw.get("temperature"))
    hum = _to_float(raw.get("humidity"))
    smoke = _to_float(raw.get("smoke_level"))
    window_open = _to_bool(raw.get("window_status"))
    cooling_on = _to_bool(raw.get("cooling_status"))

    err: str | None = None
    ok = particle_configured
    if not particle_configured:
        ok = False
        err = "Configure PARTICLE_ACCESS_TOKEN and PARTICLE_DEVICE_ID"
    elif all(v is None for v in raw.values()):
        ok = False
        err = "No data from Particle (check device online and variable names)"

    return SensorSnapshot(
        timestamp_iso=now,
        temperature=temp,
        humidity=hum,
        smoke_level=smoke,
        smoke_category=categorize_smoke_level(smoke),
        window_open=window_open,
        cooling_on=cooling_on,
        particle_ok=ok,
        error_message=err,
    )


def snapshot_to_csv_row(snapshot: SensorSnapshot) -> dict[str, str]:
    """Flat strings for CSV writing."""

    def fmt_bool(b: bool | None) -> str:
        if b is None:
            return ""
        return "1" if b else "0"

    return {
        "timestamp_iso": snapshot.timestamp_iso,
        "temperature": "" if snapshot.temperature is None else str(snapshot.temperature),
        "humidity": "" if snapshot.humidity is None else str(snapshot.humidity),
        "smoke_level": "" if snapshot.smoke_level is None else str(snapshot.smoke_level),
        "smoke_category": snapshot.smoke_category or "",
        "window_open": fmt_bool(snapshot.window_open),
        "cooling_on": fmt_bool(snapshot.cooling_on),
    }


def snapshot_to_json(snapshot: SensorSnapshot) -> dict[str, Any]:
    """Payload for /api/latest."""
    return {
        "timestamp_iso": snapshot.timestamp_iso,
        "temperature": snapshot.temperature,
        "humidity": snapshot.humidity,
        "smoke_level": snapshot.smoke_level,
        "smoke_category": snapshot.smoke_category,
        "window_open": snapshot.window_open,
        "window_status_label": _window_label(snapshot.window_open),
        "cooling_on": snapshot.cooling_on,
        "cooling_status_label": _cooling_label(snapshot.cooling_on),
        "particle_ok": snapshot.particle_ok,
        "error_message": snapshot.error_message,
    }


def _window_label(open_: bool | None) -> str:
    if open_ is None:
        return "Unknown"
    return "Open" if open_ else "Closed"


def _cooling_label(on: bool | None) -> str:
    if on is None:
        return "Unknown"
    return "On" if on else "Off"
