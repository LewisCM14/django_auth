"""Tests for config/logging.py — JsonFormatter."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

import pytest

from config.logging import JsonFormatter


@pytest.fixture()
def formatter() -> JsonFormatter:
    return JsonFormatter()


def _make_record(msg: str = "hello", **extras: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extras.items():
        setattr(record, key, value)
    return record


class TestJsonFormatter:
    """Tests for JsonFormatter output structure and field mapping."""

    def test_output_shape(self, formatter: JsonFormatter) -> None:
        """Formatted output is valid JSON with all required keys."""
        record = _make_record("test message")
        output = json.loads(formatter.format(record))

        assert set(output.keys()) == {
            "timestamp",
            "level",
            "logger",
            "request_id",
            "message",
        }

    def test_includes_request_id_from_record(self, formatter: JsonFormatter) -> None:
        """request_id from the log record extras appears in the JSON output."""
        known_id = "abc-123"
        record = _make_record("msg", request_id=known_id)
        output = json.loads(formatter.format(record))

        assert output["request_id"] == known_id

    def test_defaults_request_id_when_absent(self, formatter: JsonFormatter) -> None:
        """request_id defaults to '-' when not set on the record."""
        record = _make_record("msg")
        output = json.loads(formatter.format(record))

        assert output["request_id"] == "-"

    def test_correct_level_and_logger(self, formatter: JsonFormatter) -> None:
        """level and logger fields reflect the log record's values."""
        record = _make_record("msg")
        output = json.loads(formatter.format(record))

        assert output["level"] == "INFO"
        assert output["logger"] == "test.logger"

    def test_message_content(self, formatter: JsonFormatter) -> None:
        """message field contains the formatted log message."""
        record = _make_record("hello world")
        output = json.loads(formatter.format(record))

        assert output["message"] == "hello world"

    def test_includes_security_fields_with_utc_timestamp(
        self, formatter: JsonFormatter
    ) -> None:
        """Structured security fields are preserved and timestamp is UTC ISO 8601."""
        record = _make_record(
            "authentication succeeded",
            request_id="req-123",
            event_type="AUTHENTICATION_SUCCESS",
            user_identifier="DOMAIN\\user",
            source_ip="203.0.113.10",
            user_agent="pytest-agent",
            action_attempted="authenticate REMOTE_USER",
            result="success",
            resource_accessed="/api/user/",
            status_code=200,
            duration_ms=12.3,
        )
        output = json.loads(formatter.format(record))

        parsed_timestamp = datetime.fromisoformat(
            output["timestamp"].replace("Z", "+00:00")
        )

        assert parsed_timestamp.tzinfo == timezone.utc
        assert output["event_type"] == "AUTHENTICATION_SUCCESS"
        assert output["user_identifier"] == "DOMAIN\\user"
        assert output["source_ip"] == "203.0.113.10"
        assert output["user_agent"] == "pytest-agent"
        assert output["action_attempted"] == "authenticate REMOTE_USER"
        assert output["result"] == "success"
        assert output["resource_accessed"] == "/api/user/"
        assert output["status_code"] == 200
        assert output["duration_ms"] == 12.3

    def test_format_time_honors_custom_datefmt(self, formatter: JsonFormatter) -> None:
        """Custom date formats use the UTC timestamp branch."""
        record = _make_record("msg")
        formatted = formatter.formatTime(record, "%Y-%m-%d")

        assert formatted == datetime.fromtimestamp(
            record.created, tz=timezone.utc
        ).strftime("%Y-%m-%d")
