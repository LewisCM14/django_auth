"""Tests for the Oracle adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from api.adapters.oracle import (
    OracleAdapter,
    OracleAdapterConfig,
    create_oracle_adapter_from_env,
)


class FakeDatabaseError(Exception):
    """Fake driver error type used in adapter tests."""


@dataclass
class FakeErrorDetails:
    """Fake Oracle error details with a code attribute."""

    code: int


class FakeCursor:
    """Fake Oracle cursor that supports context manager usage."""

    def __init__(
        self,
        *,
        rows: list[tuple[object, ...]],
        description: list[tuple[object, ...]],
        errors: list[Exception] | None = None,
    ) -> None:
        self.description = description
        self.rows = rows
        self.errors = errors or []
        self.executed: list[tuple[str, object]] = []
        self.arraysize = 0
        self.prefetchrows = 0

    def execute(self, statement: str, parameters: object = None) -> object:
        self.executed.append((statement, parameters))
        if self.errors:
            raise self.errors.pop(0)
        return object()

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.rows)

    def fetchone(self) -> tuple[object, ...] | None:
        if not self.rows:
            return None
        return self.rows[0]

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class FakeConnection:
    """Fake Oracle connection with cursor factory."""

    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.call_timeout = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class FakePool:
    """Fake Oracle pool used to validate adapter behavior."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.acquire_count = 0
        self.closed_force: bool | None = None

    def acquire(self) -> FakeConnection:
        self.acquire_count += 1
        return self._connection

    def close(self, force: bool = False) -> None:
        self.closed_force = force


class FakeDriver:
    """Fake Oracle driver module interface."""

    DatabaseError: type[Exception] = FakeDatabaseError
    POOL_GETMODE_WAIT: object = "wait"

    def __init__(self, pool: FakePool) -> None:
        self._pool = pool
        self.create_pool_kwargs: dict[str, object] = {}

    def create_pool(self, **kwargs: object) -> Any:
        self.create_pool_kwargs = kwargs
        return self._pool


class FakeCache:
    """Simple in-memory cache double with call tracking."""

    def __init__(self) -> None:
        self._store: dict[str, object] = {}
        self.set_calls: list[tuple[str, object, int | None]] = []

    def get(self, key: str, default: object = None) -> object:
        return self._store.get(key, default)

    def set(self, key: str, value: object, timeout: int | None = None) -> None:
        self._store[key] = value
        self.set_calls.append((key, value, timeout))


def _base_config(**overrides: Any) -> OracleAdapterConfig:
    base = OracleAdapterConfig(
        username="app_user",
        password="secret",
        dsn="tcps://db.example.com:1522/APP",
        call_timeout_ms=12345,
        arraysize=64,
        prefetch_rows=64,
        max_retry_attempts=3,
        retry_backoff_seconds=0.1,
    )
    return replace(base, **overrides)


class TestOracleAdapterConfig:
    """Tests for Oracle adapter configuration parsing."""

    def test_from_env_builds_config(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
            "ORACLE_POOL_MIN_CONNECTIONS": "2",
            "ORACLE_POOL_MAX_CONNECTIONS": "12",
            "ORACLE_RETRY_BACKOFF_SECONDS": "0.5",
            "ORACLE_CACHE_ENABLED": "true",
            "ORACLE_CACHE_TTL_SECONDS": "45",
        }

        config = OracleAdapterConfig.from_env(env)

        assert config.username == "app_user"
        assert config.pool_min_connections == 2
        assert config.pool_max_connections == 12
        assert config.retry_backoff_seconds == 0.5
        assert config.cache_enabled is True
        assert config.cache_ttl_seconds == 45

    def test_from_env_requires_username(self) -> None:
        env = {
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
        }

        with pytest.raises(ImproperlyConfigured, match="ORACLE_USERNAME"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_rejects_non_integer(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
            "ORACLE_POOL_MIN_CONNECTIONS": "not-an-int",
        }

        with pytest.raises(ImproperlyConfigured, match="ORACLE_POOL_MIN_CONNECTIONS"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_rejects_integer_below_minimum(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
            "ORACLE_POOL_MAX_CONNECTIONS": "0",
        }

        with pytest.raises(ImproperlyConfigured, match="ORACLE_POOL_MAX_CONNECTIONS"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_rejects_non_float(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
            "ORACLE_RETRY_BACKOFF_SECONDS": "not-a-float",
        }

        with pytest.raises(ImproperlyConfigured, match="ORACLE_RETRY_BACKOFF_SECONDS"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_rejects_float_below_minimum(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
            "ORACLE_RETRY_BACKOFF_SECONDS": "-0.1",
        }

        with pytest.raises(ImproperlyConfigured, match="ORACLE_RETRY_BACKOFF_SECONDS"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_rejects_invalid_bool(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
            "ORACLE_CACHE_ENABLED": "sometimes",
        }

        with pytest.raises(ImproperlyConfigured, match="ORACLE_CACHE_ENABLED"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_accepts_false_bool(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
            "ORACLE_CACHE_ENABLED": "0",
        }

        config = OracleAdapterConfig.from_env(env)

        assert config.cache_enabled is False

    def test_from_env_rejects_privileged_username(self) -> None:
        env = {
            "ORACLE_USERNAME": "SYSTEM",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
        }

        with pytest.raises(ImproperlyConfigured, match="least-privilege"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_rejects_invalid_username_format(self) -> None:
        env = {
            "ORACLE_USERNAME": "bad/user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "tcps://db.example.com:1522/APP",
        }

        with pytest.raises(ImproperlyConfigured, match="strict allowlist"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_rejects_non_tls_dsn_when_tls_required(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "db.example.com:1521/APP",
        }

        with pytest.raises(ImproperlyConfigured, match="TLS/TCPS"):
            OracleAdapterConfig.from_env(env)

    def test_from_env_allows_non_tls_dsn_when_tls_opt_out(self) -> None:
        env = {
            "ORACLE_USERNAME": "app_user",
            "ORACLE_PASSWORD": "secret",
            "ORACLE_DSN": "db.example.com:1521/APP",
            "ORACLE_REQUIRE_TLS": "false",
        }

        config = OracleAdapterConfig.from_env(env)

        assert config.require_tls is False
        assert config.dsn == "db.example.com:1521/APP"


class TestOracleAdapter:
    """Tests for query execution and retry behavior."""

    def test_fetch_all_returns_dict_rows(self) -> None:
        cursor = FakeCursor(
            rows=[("A100", "Paid"), ("A101", "Open")],
            description=[("INVOICE_ID",), ("STATUS",)],
        )
        connection = FakeConnection(cursor)
        pool = FakePool(connection)
        driver = FakeDriver(pool)

        adapter = OracleAdapter(_base_config(), driver=driver)
        rows = adapter.fetch_all(
            "SELECT invoice_id, status FROM invoices WHERE status = :status",
            {"status": "Paid"},
        )

        assert rows == [
            {"invoice_id": "A100", "status": "Paid"},
            {"invoice_id": "A101", "status": "Open"},
        ]
        assert connection.call_timeout == 12345
        assert cursor.arraysize == 64
        assert cursor.prefetchrows == 64
        assert pool.acquire_count == 1

    def test_fetch_all_logs_structured_success_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cursor = FakeCursor(
            rows=[("A100", "Paid")],
            description=[("INVOICE_ID",), ("STATUS",)],
        )
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )
        captured: dict[str, object] = {}

        def capture_info(message: str, *args: object, **kwargs: object) -> None:
            del args
            captured["message"] = message
            captured["kwargs"] = kwargs

        monkeypatch.setattr("api.adapters.oracle.logger.info", capture_info)

        adapter.fetch_all(
            "SELECT invoice_id, status FROM invoices WHERE status = :status",
            {"status": "Paid"},
        )

        assert captured["message"] == "oracle query completed"
        kwargs = captured["kwargs"]
        assert isinstance(kwargs, dict)
        extra = kwargs.get("extra")
        assert isinstance(extra, dict)
        assert extra["event_type"] == "ORACLE_QUERY_SUCCESS"
        assert extra["action_attempted"] == "execute oracle read query"
        assert extra["resource_accessed"] == "oracle:read"
        assert extra["result"] == "success"
        assert extra["oracle_row_count"] == 1
        assert isinstance(extra["oracle_query_id"], str)
        assert isinstance(extra["duration_ms"], float)

    def test_fetch_all_uses_adapter_cache_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cursor = FakeCursor(
            rows=[("A100", "Paid")],
            description=[("INVOICE_ID",), ("STATUS",)],
        )
        pool = FakePool(FakeConnection(cursor))
        fake_cache = FakeCache()
        monkeypatch.setattr("api.adapters.oracle.cache", fake_cache)

        adapter = OracleAdapter(
            _base_config(cache_enabled=True, cache_ttl_seconds=45),
            driver=FakeDriver(pool),
        )
        sql = "SELECT invoice_id, status FROM invoices WHERE status = :status"
        params = {"status": "Paid"}

        first_rows = adapter.fetch_all(sql, params)
        first_rows[0]["status"] = "Mutated"
        second_rows = adapter.fetch_all(sql, params)

        assert pool.acquire_count == 1
        assert second_rows == [{"invoice_id": "A100", "status": "Paid"}]
        assert len(fake_cache.set_calls) == 1
        assert fake_cache.set_calls[0][2] == 45

    def test_fetch_one_caches_none_result_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cursor = FakeCursor(rows=[], description=[("INVOICE_ID",)])
        pool = FakePool(FakeConnection(cursor))
        fake_cache = FakeCache()
        monkeypatch.setattr("api.adapters.oracle.cache", fake_cache)

        adapter = OracleAdapter(
            _base_config(cache_enabled=True),
            driver=FakeDriver(pool),
        )
        sql = "SELECT invoice_id FROM invoices WHERE invoice_id = :invoice_id"
        params = {"invoice_id": "A100"}

        first = adapter.fetch_one(sql, params)
        second = adapter.fetch_one(sql, params)

        assert first is None
        assert second is None
        assert pool.acquire_count == 1

    def test_fetch_all_uses_cache_with_sequence_params(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cursor = FakeCursor(
            rows=[("A100",)],
            description=[("INVOICE_ID",)],
        )
        pool = FakePool(FakeConnection(cursor))
        fake_cache = FakeCache()
        monkeypatch.setattr("api.adapters.oracle.cache", fake_cache)

        adapter = OracleAdapter(
            _base_config(cache_enabled=True),
            driver=FakeDriver(pool),
        )
        sql = "SELECT invoice_id FROM invoices WHERE status = :1"
        params = ["Paid"]

        first = adapter.fetch_all(sql, params)
        second = adapter.fetch_all(sql, params)

        assert first == [{"invoice_id": "A100"}]
        assert second == [{"invoice_id": "A100"}]
        assert pool.acquire_count == 1

    def test_fetch_all_continues_when_cache_lookup_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class BrokenCache:
            def get(self, _key: str, _default: object = None) -> object:
                raise RuntimeError("cache lookup unavailable")

            def set(
                self,
                _key: str,
                _value: object,
                timeout: int | None = None,
            ) -> None:
                del timeout

        cursor = FakeCursor(
            rows=[("A100",)],
            description=[("INVOICE_ID",)],
        )
        pool = FakePool(FakeConnection(cursor))
        monkeypatch.setattr("api.adapters.oracle.cache", BrokenCache())

        adapter = OracleAdapter(
            _base_config(cache_enabled=True),
            driver=FakeDriver(pool),
        )

        rows = adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert rows == [{"invoice_id": "A100"}]
        assert pool.acquire_count == 1

    def test_fetch_one_returns_none_when_no_rows(self) -> None:
        cursor = FakeCursor(rows=[], description=[("ID",)])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        result = adapter.fetch_one("SELECT id FROM invoices")

        assert result is None

    def test_fetch_one_returns_dict_row(self) -> None:
        cursor = FakeCursor(rows=[("A100",)], description=[("INVOICE_ID",)])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        result = adapter.fetch_one("SELECT invoice_id FROM invoices")

        assert result == {"invoice_id": "A100"}

    def test_fetch_all_rejects_non_read_sql(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="read-only"):
            adapter.fetch_all("DELETE FROM invoices")

    def test_fetch_all_rejects_blank_sql(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="non-empty"):
            adapter.fetch_all("   ")

    def test_fetch_all_rejects_non_string_sql(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="non-empty"):
            adapter.fetch_all(123)  # type: ignore[arg-type]  # Intentional non-str SQL to verify runtime input validation.

    def test_fetch_all_rejects_statement_delimiter(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="statement delimiters"):
            adapter.fetch_all("SELECT invoice_id FROM invoices;")

    def test_fetch_all_rejects_overlong_sql(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )
        too_long_statement = "SELECT " + ("A" * 20001)

        with pytest.raises(ValueError, match="maximum length"):
            adapter.fetch_all(too_long_statement)

    def test_fetch_all_rejects_sql_with_nul_character(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="NUL"):
            adapter.fetch_all("SELECT invoice_id\x00 FROM invoices")

    def test_fetch_all_rejects_string_params_payload(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="sequence of values"):
            adapter.fetch_all("SELECT invoice_id FROM invoices", "raw-string")

    def test_fetch_all_rejects_invalid_named_bind_parameter(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="named bind parameters"):
            adapter.fetch_all("SELECT invoice_id FROM invoices", {"bad-key": "A100"})

    def test_fetch_all_rejects_unsupported_parameter_type(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="scalar values"):
            adapter.fetch_all(
                "SELECT invoice_id FROM invoices",
                {"invoice_id": SimpleNamespace(value="A100")},
            )

    def test_fetch_all_rejects_too_many_named_parameters(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )
        params = {f"p{i}": i for i in range(101)}

        with pytest.raises(ValueError, match="maximum of 100"):
            adapter.fetch_all("SELECT invoice_id FROM invoices", params)

    def test_fetch_all_rejects_too_many_positional_parameters(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )
        params = list(range(101))

        with pytest.raises(ValueError, match="maximum of 100"):
            adapter.fetch_all(
                "SELECT invoice_id FROM invoices WHERE status = :1", params
            )

    def test_fetch_all_rejects_invalid_parameter_container_type(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        with pytest.raises(ValueError, match="mapping, a sequence, or None"):
            adapter.fetch_all("SELECT invoice_id FROM invoices", 123)  # type: ignore[arg-type]  # Intentional non-container params to verify runtime input validation.

    def test_fetch_all_rejects_overlong_string_parameter(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )
        long_value = "A" * 4001

        with pytest.raises(ValueError, match="string parameter length"):
            adapter.fetch_all(
                "SELECT invoice_id FROM invoices WHERE invoice_id = :invoice_id",
                {"invoice_id": long_value},
            )

    def test_fetch_all_rejects_overlong_binary_parameter(self) -> None:
        cursor = FakeCursor(rows=[], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )
        long_blob = b"A" * 65536

        with pytest.raises(ValueError, match="binary parameter length"):
            adapter.fetch_all(
                "SELECT invoice_id FROM invoices WHERE invoice_blob = :blob",
                {"blob": long_blob},
            )

    def test_fetch_all_supports_empty_description(self) -> None:
        cursor = FakeCursor(rows=[("A100",)], description=[])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        rows = adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert rows == [{}]

    def test_fetch_all_uses_fallback_column_names(self) -> None:
        cursor = FakeCursor(rows=[("A100",)], description=[("",)])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        rows = adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert rows == [{"column_1": "A100"}]

    def test_fetch_all_retries_transient_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transient_error = FakeDatabaseError(FakeErrorDetails(code=12541))
        cursor = FakeCursor(
            rows=[("A100",)],
            description=[("INVOICE_ID",)],
            errors=[transient_error],
        )
        pool = FakePool(FakeConnection(cursor))
        adapter = OracleAdapter(_base_config(), driver=FakeDriver(pool))

        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "api.adapters.oracle.time.sleep",
            lambda seconds: sleep_calls.append(seconds),
        )

        rows = adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert rows == [{"invoice_id": "A100"}]
        assert pool.acquire_count == 2
        assert sleep_calls == [0.1]

    def test_fetch_all_does_not_retry_non_transient_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        non_transient_error = FakeDatabaseError(FakeErrorDetails(code=942))
        cursor = FakeCursor(
            rows=[],
            description=[("INVOICE_ID",)],
            errors=[non_transient_error],
        )
        pool = FakePool(FakeConnection(cursor))
        adapter = OracleAdapter(_base_config(), driver=FakeDriver(pool))

        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "api.adapters.oracle.time.sleep",
            lambda seconds: sleep_calls.append(seconds),
        )

        with pytest.raises(FakeDatabaseError):
            adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert pool.acquire_count == 1
        assert sleep_calls == []

    def test_fetch_all_retries_when_error_code_is_in_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transient_error = FakeDatabaseError("ORA-12541: TNS:no listener")
        cursor = FakeCursor(
            rows=[("A100",)],
            description=[("INVOICE_ID",)],
            errors=[transient_error],
        )
        pool = FakePool(FakeConnection(cursor))
        adapter = OracleAdapter(_base_config(), driver=FakeDriver(pool))

        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "api.adapters.oracle.time.sleep",
            lambda seconds: sleep_calls.append(seconds),
        )

        rows = adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert rows == [{"invoice_id": "A100"}]
        assert pool.acquire_count == 2
        assert sleep_calls == [0.1]

    def test_fetch_all_does_not_retry_when_error_code_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unknown_error = FakeDatabaseError("driver crashed without ORA code")
        cursor = FakeCursor(
            rows=[],
            description=[("INVOICE_ID",)],
            errors=[unknown_error],
        )
        pool = FakePool(FakeConnection(cursor))
        adapter = OracleAdapter(_base_config(), driver=FakeDriver(pool))

        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "api.adapters.oracle.time.sleep",
            lambda seconds: sleep_calls.append(seconds),
        )

        with pytest.raises(FakeDatabaseError):
            adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert pool.acquire_count == 1
        assert sleep_calls == []

    def test_fetch_all_logs_and_raises_non_driver_exceptions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cursor = FakeCursor(
            rows=[],
            description=[("INVOICE_ID",)],
            errors=[RuntimeError("unexpected failure")],
        )
        pool = FakePool(FakeConnection(cursor))
        adapter = OracleAdapter(_base_config(), driver=FakeDriver(pool))
        captured: dict[str, object] = {}

        def capture_exception(message: str, *args: object, **kwargs: object) -> None:
            del args
            captured["message"] = message
            captured["kwargs"] = kwargs

        monkeypatch.setattr("api.adapters.oracle.logger.exception", capture_exception)

        with pytest.raises(RuntimeError, match="unexpected failure"):
            adapter.fetch_all("SELECT invoice_id FROM invoices")

        assert captured["message"] == "oracle query failed with non-driver exception"

    def test_fetch_one_executes_with_params(self) -> None:
        cursor = FakeCursor(rows=[("A100",)], description=[("INVOICE_ID",)])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        result = adapter.fetch_one(
            "SELECT invoice_id FROM invoices WHERE invoice_id = :invoice_id",
            {"invoice_id": "A100"},
        )

        assert result == {"invoice_id": "A100"}
        assert cursor.executed[-1][1] == {"invoice_id": "A100"}

    def test_close_closes_pool(self) -> None:
        pool = FakePool(FakeConnection(FakeCursor(rows=[], description=[])))
        adapter = OracleAdapter(_base_config(), driver=FakeDriver(pool))

        adapter.close()

        assert pool.closed_force is True

    def test_fetch_all_async_returns_rows(self) -> None:
        cursor = FakeCursor(
            rows=[("A100", "Paid")],
            description=[("INVOICE_ID",), ("STATUS",)],
        )
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        rows = asyncio.run(
            adapter.fetch_all_async(
                "SELECT invoice_id, status FROM invoices WHERE status = :status",
                {"status": "Paid"},
            )
        )

        assert rows == [{"invoice_id": "A100", "status": "Paid"}]

    def test_fetch_one_async_returns_row(self) -> None:
        cursor = FakeCursor(rows=[("A100",)], description=[("INVOICE_ID",)])
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )

        row = asyncio.run(adapter.fetch_one_async("SELECT invoice_id FROM invoices"))

        assert row == {"invoice_id": "A100"}

    def test_close_async_closes_pool(self) -> None:
        pool = FakePool(FakeConnection(FakeCursor(rows=[], description=[])))
        adapter = OracleAdapter(_base_config(), driver=FakeDriver(pool))

        asyncio.run(adapter.close_async())

        assert pool.closed_force is True

    def test_fetch_all_async_uses_sync_to_async(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cursor = FakeCursor(
            rows=[("A100",)],
            description=[("INVOICE_ID",)],
        )
        adapter = OracleAdapter(
            _base_config(),
            driver=FakeDriver(FakePool(FakeConnection(cursor))),
        )
        captured: dict[str, object] = {}

        def fake_sync_to_async(func: object, *, thread_sensitive: bool) -> object:
            captured["func"] = func
            captured["thread_sensitive"] = thread_sensitive

            async def runner(*args: object, **kwargs: object) -> object:
                assert callable(func)
                return func(*args, **kwargs)

            return runner

        monkeypatch.setattr("api.adapters.oracle.sync_to_async", fake_sync_to_async)

        rows = asyncio.run(adapter.fetch_all_async("SELECT invoice_id FROM invoices"))

        assert rows == [{"invoice_id": "A100"}]
        assert captured["thread_sensitive"] is False


class TestOracleAdapterFactory:
    """Tests for adapter factory behavior."""

    def test_create_oracle_adapter_from_env_uses_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pool = FakePool(FakeConnection(FakeCursor(rows=[], description=[])))
        driver = FakeDriver(pool)
        monkeypatch.setenv("ORACLE_USERNAME", "app_user")
        monkeypatch.setenv("ORACLE_PASSWORD", "secret")
        monkeypatch.setenv("ORACLE_DSN", "tcps://db.example.com:1522/APP")

        adapter = create_oracle_adapter_from_env(driver=driver)

        assert isinstance(adapter, OracleAdapter)
        assert driver.create_pool_kwargs["dsn"] == "tcps://db.example.com:1522/APP"

    def test_adapter_init_loads_driver_when_none_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pool = FakePool(FakeConnection(FakeCursor(rows=[], description=[])))
        driver = FakeDriver(pool)
        monkeypatch.setattr(
            "api.adapters.oracle.importlib.import_module",
            lambda _name: driver,
        )

        adapter = OracleAdapter(_base_config(), driver=None)

        assert isinstance(adapter, OracleAdapter)
        assert driver.create_pool_kwargs["dsn"] == "tcps://db.example.com:1522/APP"

    def test_adapter_init_raises_if_oracle_driver_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "api.adapters.oracle.importlib.import_module",
            lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("oracledb")),
        )

        with pytest.raises(ImproperlyConfigured, match="python-oracledb"):
            OracleAdapter(_base_config(), driver=None)
