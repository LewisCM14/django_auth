"""Custom logging formatters for the authentication service.

Kept separate from settings.py so that formatter classes can be imported,
instantiated, and tested in isolation without triggering settings validation
(SECRET_KEY guards, AUTH_MODE checks, etc.).
"""

from __future__ import annotations

import json
import logging


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured, machine-parseable log output.

    Emits a single-line JSON object with keys: timestamp, level, logger,
    request_id, and message. The request_id field is populated from the
    log record's extras (injected by RequestIdFilter), defaulting to "-"
    when no request context is available (e.g., startup, management commands).
    """

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "request_id": getattr(record, "request_id", "-"),
                "message": record.getMessage(),
            }
        )
