"""Custom logging formatters for the authentication service.

Kept separate from settings.py so that formatter classes can be imported,
instantiated, and tested in isolation without triggering settings validation
(SECRET_KEY guards, AUTH_MODE checks, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from api.security_logging import SECURITY_EXTRA_FIELDS


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured, machine-parseable log output.

    Emits a single-line JSON object with keys: timestamp, level, logger,
    request_id, and message. The request_id field is populated from the
    log record's extras (injected by RequestIdFilter), defaulting to "-"
    when no request context is available (e.g., startup, management commands).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }

        for field_name in SECURITY_EXTRA_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value

        return json.dumps(payload)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt is not None:
            return timestamp.strftime(datefmt)
        return timestamp.isoformat().replace("+00:00", "Z")
