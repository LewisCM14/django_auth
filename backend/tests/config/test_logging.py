"""Tests for config/logging.py — JsonFormatter."""

from __future__ import annotations

import json
import logging

import pytest

from config.logging import JsonFormatter


@pytest.fixture()
def formatter() -> JsonFormatter:
    return JsonFormatter()


def _make_record(msg: str = "hello", **extras: str) -> logging.LogRecord:
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


def test_json_formatter_output_shape(formatter: JsonFormatter) -> None:
    """Formatted output is valid JSON with all required keys."""
    record = _make_record("test message")
    output = json.loads(formatter.format(record))

    assert set(output.keys()) == {"timestamp", "level", "logger", "request_id", "message"}


def test_json_formatter_includes_request_id_from_record(formatter: JsonFormatter) -> None:
    """request_id from the log record extras appears in the JSON output."""
    known_id = "abc-123"
    record = _make_record("msg", request_id=known_id)
    output = json.loads(formatter.format(record))

    assert output["request_id"] == known_id


def test_json_formatter_defaults_request_id_when_absent(formatter: JsonFormatter) -> None:
    """request_id defaults to '-' when not set on the record."""
    record = _make_record("msg")
    output = json.loads(formatter.format(record))

    assert output["request_id"] == "-"


def test_json_formatter_correct_level_and_logger(formatter: JsonFormatter) -> None:
    """level and logger fields reflect the log record's values."""
    record = _make_record("msg")
    output = json.loads(formatter.format(record))

    assert output["level"] == "INFO"
    assert output["logger"] == "test.logger"


def test_json_formatter_message_content(formatter: JsonFormatter) -> None:
    """message field contains the formatted log message."""
    record = _make_record("hello world")
    output = json.loads(formatter.format(record))

    assert output["message"] == "hello world"
