import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def build_particle_variable_orders() -> dict[str, tuple[str, ...]]:
    """
    Particle Cloud variable names to try per dashboard field (first match wins).

    Override any column with PARTICLE_VAR_* in the environment (exact cloud name).
    """
    # Order matters: first HTTP 200 wins. farm-iot.ino uses PascalCase Particle.variable names.
    defaults: dict[str, tuple[str, ...]] = {
        "temperature": ("Temperature", "temperature", "temp"),
        "humidity": ("Humidity", "humidity", "hum", "relativeHumidity", "rh", "RH"),
        "smoke_level": ("SmokeLevel", "smoke_level", "smoke", "gas", "MQ2", "mq2"),
        # farm-iot.ino exposes WindowOpen / CoolingOn (int 0/1) on the Argon / polled device.
        "window_status": ("WindowOpen", "window_status", "window", "WindowStatus"),
        "cooling_status": ("CoolingOn", "cooling_status", "cooling", "CoolingStatus", "fan", "Fan"),
    }
    overrides = {
        "temperature": "PARTICLE_VAR_TEMPERATURE",
        "humidity": "PARTICLE_VAR_HUMIDITY",
        "smoke_level": "PARTICLE_VAR_SMOKE",
        "window_status": "PARTICLE_VAR_WINDOW_STATUS",
        "cooling_status": "PARTICLE_VAR_COOLING_STATUS",
    }
    out: dict[str, tuple[str, ...]] = {}
    for canon, names in defaults.items():
        key = overrides.get(canon)
        raw = os.environ.get(key, "").strip() if key else ""
        if raw:
            rest = tuple(n for n in names if n != raw)
            out[canon] = (raw,) + rest
        else:
            out[canon] = names
    return out


def load_settings() -> dict:
    """Load runtime settings from environment variables."""
    return {
        "particle_access_token": os.environ.get("PARTICLE_ACCESS_TOKEN", "").strip(),
        "particle_device_id": os.environ.get("PARTICLE_DEVICE_ID", "").strip(),
        "poll_interval_seconds": max(5, _int_env("POLL_INTERVAL_SECONDS", 30)),
        "csv_path": os.environ.get(
            "SENSOR_CSV_PATH",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "model", "sensor_history.csv"),
        ),
        "particle_api_base": os.environ.get(
            "PARTICLE_API_BASE", "https://api.particle.io/v1"
        ).rstrip("/"),
        "particle_variable_orders": build_particle_variable_orders(),
    }
