import logging
import threading
from typing import Any

from flask import Flask, jsonify, render_template

from modules.config import load_settings
from modules.logging_config import configure_logging
from modules.particle_poll import poll_device_variables
from modules.processing import SensorSnapshot, build_snapshot, snapshot_to_json
from modules.storage import append_snapshot, count_records

log = logging.getLogger(__name__)
_logging_ready = False

app = Flask(__name__)

_settings: dict[str, Any] = {}
_lock = threading.Lock()
_poller_lock = threading.Lock()
_latest: SensorSnapshot | None = None
_poll_thread: threading.Thread | None = None
_stop_poll = threading.Event()
_poller_started = False


def _particle_configured() -> bool:
    return bool(_settings.get("particle_access_token") and _settings.get("particle_device_id"))


def _ensure_logging_configured() -> None:
    global _logging_ready
    if _logging_ready:
        return
    configure_logging()
    _logging_ready = True


def _snapshot_log_summary(snap: SensorSnapshot) -> str:
    return (
        f"temperature={snap.temperature} humidity={snap.humidity} "
        f"smoke_level={snap.smoke_level} category={snap.smoke_category!r} "
        f"window_open={snap.window_open} cooling_on={snap.cooling_on}"
    )


def _poll_loop() -> None:
    interval = int(_settings.get("poll_interval_seconds", 30))
    csv_path = str(_settings.get("csv_path", ""))

    while not _stop_poll.is_set():
        if _particle_configured():
            raw: dict[str, Any | None] = poll_device_variables(
                _settings["particle_device_id"],
                _settings["particle_access_token"],
                api_base=_settings["particle_api_base"],
                variable_orders=_settings["particle_variable_orders"],
            )
        else:
            raw = dict.fromkeys(
                ("temperature", "humidity", "smoke_level", "window_status", "cooling_status"),
                None,
            )

        snap = build_snapshot(raw, particle_configured=_particle_configured())

        device_hint = _settings.get("particle_device_id") or ""
        if len(device_hint) > 12:
            device_hint = f"{device_hint[:8]}…"

        log.debug("Particle raw variables: %s", raw)

        if snap.particle_ok:
            log.info(
                "[poll] ok device=%s | %s",
                device_hint or "(not configured)",
                _snapshot_log_summary(snap),
            )
        elif _particle_configured():
            log.warning(
                "[poll] incomplete device=%s err=%s | %s",
                device_hint or "(not configured)",
                snap.error_message,
                _snapshot_log_summary(snap),
            )
        else:
            log.debug(
                "[poll] idle (Particle not configured) err=%s | %s",
                snap.error_message,
                _snapshot_log_summary(snap),
            )

        if _particle_configured() and snap.particle_ok:
            try:
                append_snapshot(csv_path, snap)
                log.debug("CSV append persisted path=%s", csv_path)
            except OSError as exc:
                log.error("CSV write failed path=%s: %s", csv_path, exc)

        with _lock:
            global _latest
            _latest = snap

        if _stop_poll.wait(timeout=interval):
            break


def ensure_poller_started() -> None:
    """Start the Particle polling thread once (safe with Flask debug reloader)."""
    global _settings, _poll_thread, _poller_started
    _ensure_logging_configured()
    if _poller_started:
        return
    with _poller_lock:
        if _poller_started:
            return
        _settings = load_settings()
        dev = _settings.get("particle_device_id") or ""
        dev_log = dev if len(dev) <= 16 else f"{dev[:12]}…"
        log.info(
            "[startup] poller thread | particle_device=%s configured=%s | poll_interval=%ss "
            "| csv=%s | api_base=%s",
            dev_log or "(none)",
            _particle_configured(),
            _settings.get("poll_interval_seconds"),
            _settings.get("csv_path"),
            _settings.get("particle_api_base"),
        )
        _stop_poll.clear()
        _poll_thread = threading.Thread(target=_poll_loop, name="particle-poller", daemon=True)
        _poll_thread.start()
        _poller_started = True


@app.before_request
def _bootstrap_poller():
    ensure_poller_started()


@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/api/latest")
def api_latest():
    log.debug("GET /api/latest")
    with _lock:
        snap = _latest
    if snap is None:
        return jsonify(
            {
                "timestamp_iso": None,
                "temperature": None,
                "humidity": None,
                "smoke_level": None,
                "smoke_category": None,
                "window_open": None,
                "window_status_label": "Unknown",
                "cooling_on": None,
                "cooling_status_label": "Unknown",
                "particle_ok": False,
                "error_message": "Waiting for first poll…",
            }
        )
    return jsonify(snapshot_to_json(snap))


@app.route("/api/status")
def api_status():
    log.debug("GET /api/status")
    csv_path = str(_settings.get("csv_path", ""))
    return jsonify(
        {
            "poll_interval_seconds": _settings.get("poll_interval_seconds"),
            "stored_records": count_records(csv_path),
            "particle_configured": _particle_configured(),
            "csv_path": csv_path,
        }
    )


if __name__ == "__main__":
    _ensure_logging_configured()
    log.info("Running Flask dev server (debug=True)")
    app.run(debug=True)
