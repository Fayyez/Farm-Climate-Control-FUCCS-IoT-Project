"""Central logging setup for the Flask app and background poller."""

from __future__ import annotations

import logging
import os
import sys

_FORMAT = "%(asctime)s | %(levelname)-5s | %(threadName)s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """
    Configure root logging once. Controlled by LOG_LEVEL (default INFO).

    Uses stdout, consistent timestamps, and quiets noisy libraries unless DEBUG.
    """
    raw = os.environ.get("LOG_LEVEL", "INFO").upper().strip()
    parsed = getattr(logging, raw, None)
    level = parsed if isinstance(parsed, int) else logging.INFO

    logging.basicConfig(
        level=level,
        format=_FORMAT,
        datefmt=_DATEFMT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    # Fewer lines unless explicitly debugging HTTP stacks
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    if level <= logging.DEBUG:
        logging.getLogger("werkzeug").setLevel(logging.DEBUG)
    else:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
