from __future__ import annotations

import logging
import threading
from typing import Any, Literal, Mapping, Sequence

import requests

log = logging.getLogger(__name__)

_cloud_catalog_logged_lock = threading.Lock()
_cloud_catalog_logged = False

# Dashboard field → optional (skip noisy warnings when missing entirely).
CANONICAL_FIELDS: tuple[tuple[str, bool], ...] = (
    ("temperature", False),
    ("humidity", False),
    ("smoke_level", False),
    ("window_status", False),
    ("cooling_status", False),
)


def _device_short(device_id: str) -> str:
    if not device_id:
        return "(none)"
    return device_id if len(device_id) <= 12 else f"{device_id[:10]}…"


def _request_variable(
    device_id: str,
    particle_name: str,
    access_token: str,
    *,
    api_base: str,
    timeout_seconds: float,
) -> tuple[Any | None, Literal["ok", "missing", "error"]]:
    """GET one cloud variable; classify outcome without treating 404 as fatal."""
    url = f"{api_base}/devices/{device_id}/{particle_name}"
    dev = _device_short(device_id)
    try:
        resp = requests.get(
            url,
            params={"access_token": access_token},
            timeout=timeout_seconds,
        )
        if resp.status_code == 404:
            return None, "missing"

        if resp.status_code >= 400:
            snippet = ""
            try:
                snippet = (resp.text or "")[:180].replace("\n", " ")
            except OSError:
                snippet = "(read error)"
            log.warning(
                "Particle HTTP %s variable=%s device=%s | %s",
                resp.status_code,
                particle_name,
                dev,
                snippet,
            )
            return None, "error"

        data = resp.json()
        if "result" not in data:
            log.warning(
                "Particle unexpected JSON for variable=%s device=%s keys=%s",
                particle_name,
                dev,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            return None, "error"

        result = data["result"]
        log.debug(
            "particle variable ok device=%s particle=%s result=%r",
            dev,
            particle_name,
            result,
        )
        return result, "ok"

    except requests.Timeout as exc:
        log.warning(
            "Particle timeout variable=%s device=%s (%ss): %s",
            particle_name,
            dev,
            timeout_seconds,
            exc,
        )
        return None, "error"
    except requests.RequestException as exc:
        log.warning(
            "Particle request failed variable=%s device=%s: %s",
            particle_name,
            dev,
            exc,
        )
        return None, "error"


def fetch_variable_aliases(
    device_id: str,
    canonical: str,
    particle_names: Sequence[str],
    access_token: str,
    *,
    api_base: str,
    timeout_seconds: float = 15.0,
    optional: bool = False,
) -> Any | None:
    """Try Particle cloud names in order until one returns HTTP 200 with a result."""
    tried: list[str] = []
    for particle_name in particle_names:
        tried.append(particle_name)
        value, outcome = _request_variable(
            device_id,
            particle_name,
            access_token,
            api_base=api_base,
            timeout_seconds=timeout_seconds,
        )
        if outcome == "ok":
            log.debug("particle matched canonical=%s particle=%s", canonical, particle_name)
            return value
        if outcome == "missing":
            log.debug("particle 404 canonical=%s particle=%s", canonical, particle_name)
            continue
        return None

    if optional:
        log.debug("particle optional unresolved canonical=%s tried=%s", canonical, tried)
    else:
        log.warning(
            "Particle cloud has no variable matching dashboard field %r — tried %s. "
            "Expose names with Particle.variable() on firmware, or set PARTICLE_VAR_TEMPERATURE / "
            "PARTICLE_VAR_HUMIDITY / PARTICLE_VAR_SMOKE to the exact cloud names.",
            canonical,
            tried,
        )
    return None


def _extract_cloud_variable_names(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("variables")
    names: list[str] = []
    if isinstance(raw, dict):
        names = [str(k) for k in raw.keys()]
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
    return sorted(names)


def log_particle_cloud_catalog_once(
    device_id: str,
    access_token: str,
    *,
    api_base: str,
    timeout_seconds: float = 15.0,
) -> None:
    """If core sensors all 404, print the device's registered cloud variable names once."""
    global _cloud_catalog_logged
    with _cloud_catalog_logged_lock:
        if _cloud_catalog_logged:
            return
        _cloud_catalog_logged = True

    url = f"{api_base}/devices/{device_id}"
    dev = _device_short(device_id)
    try:
        resp = requests.get(
            url,
            params={"access_token": access_token},
            timeout=timeout_seconds,
        )
        if resp.status_code >= 400:
            log.warning(
                "Could not load Particle device metadata (%s) device=%s — check token scope and device id",
                resp.status_code,
                dev,
            )
            return
        payload = resp.json()
        names = _extract_cloud_variable_names(payload)
        if names:
            log.warning(
                "Particle cloud variables registered on device %s: %s — "
                "use these exact names in firmware (Particle.variable) or set PARTICLE_VAR_* in .env",
                dev,
                names,
            )
        else:
            log.warning(
                "Particle reports no cloud variables for device %s — "
                "sensor JSON may only be published via Particle.publish(); "
                "add Particle.variable(\"name\", handler) for HTTP polling.",
                dev,
            )
    except requests.RequestException as exc:
        log.warning("Particle device metadata request failed device=%s: %s", dev, exc)


def poll_device_variables(
    device_id: str,
    access_token: str,
    *,
    api_base: str,
    variable_orders: Mapping[str, Sequence[str]],
    timeout_seconds: float = 15.0,
) -> dict[str, Any | None]:
    """Fetch Particle variables and return keys expected by ``processing.build_snapshot``."""
    out: dict[str, Any | None] = {}
    for canonical, optional in CANONICAL_FIELDS:
        names = tuple(variable_orders.get(canonical, (canonical,)))
        out[canonical] = fetch_variable_aliases(
            device_id,
            canonical,
            names,
            access_token,
            api_base=api_base,
            timeout_seconds=timeout_seconds,
            optional=optional,
        )

    if (
        out.get("temperature") is None
        and out.get("humidity") is None
        and out.get("smoke_level") is None
    ):
        log_particle_cloud_catalog_once(device_id, access_token, api_base=api_base, timeout_seconds=timeout_seconds)

    missing = [k for k, v in out.items() if v is None]
    if missing:
        log.debug(
            "particle poll summary device=%s missing canonical keys=%s",
            _device_short(device_id),
            missing,
        )
    else:
        log.debug(
            "particle poll summary device=%s all variables present",
            _device_short(device_id),
        )

    return out
