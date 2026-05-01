"""Oracle adapter for reusable service-layer data access.

Provides pooled, retry-aware, read-only SQL execution against Oracle and
returns results as native Python dictionaries.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, TypeVar, cast

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from api.cache_keys import adapter_key
from api.middleware.request_id import request_id_var
from api.security_logging import build_security_event_fields

logger = logging.getLogger(__name__)

OracleQueryParams = Mapping[str, object] | Sequence[object] | None
OracleRow = dict[str, object]

_TRANSIENT_ORACLE_ERROR_CODES = frozenset(
    {
        3113,  # ORA-03113 end-of-file on communication channel
        3114,  # ORA-03114 not connected to Oracle
        12170,  # ORA-12170 connect timeout
        12514,  # ORA-12514 listener does not currently know of service
        12537,  # ORA-12537 TNS:connection closed
        12541,  # ORA-12541 no listener
        12543,  # ORA-12543 destination host unreachable
        12545,  # ORA-12545 target host or object does not exist
    }
)
_ORACLE_ERROR_CODE_RE = re.compile(r"ORA-(\d{5})")
_ORACLE_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_#$]{0,127}$")
_BIND_PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_TLS_DSN_PROTOCOL_RE = re.compile(r"\(PROTOCOL\s*=\s*TCPS\)", re.IGNORECASE)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_CACHE_MISS = object()
_MAX_SQL_LENGTH = 20000
_MAX_QUERY_PARAMS = 100
_MAX_STRING_PARAM_LENGTH = 4000
_MAX_BINARY_PARAM_LENGTH = 65535
_DISALLOWED_ORACLE_USERNAMES = frozenset(
    {
        "SYS",
        "SYSTEM",
        "DBSNMP",
        "SYSBACKUP",
        "SYSDG",
        "SYSKM",
        "OUTLN",
    }
)


class _OracleCursor(Protocol):
    description: Sequence[Sequence[object]] | None
    arraysize: int
    prefetchrows: int

    def execute(
        self, statement: str, parameters: OracleQueryParams = None
    ) -> object: ...

    def fetchall(self) -> Sequence[Sequence[object]]: ...

    def fetchone(self) -> Sequence[object] | None: ...

    def __enter__(self) -> "_OracleCursor": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class _OracleConnection(Protocol):
    call_timeout: int

    def cursor(self) -> _OracleCursor: ...

    def __enter__(self) -> "_OracleConnection": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class _OraclePool(Protocol):
    def acquire(self) -> _OracleConnection: ...

    def close(self, force: bool = False) -> None: ...


class _OracleDriver(Protocol):
    DatabaseError: type[Exception]
    POOL_GETMODE_WAIT: object

    def create_pool(self, **kwargs: object) -> _OraclePool: ...


def _load_oracle_driver() -> _OracleDriver:
    try:
        driver_module = importlib.import_module("oracledb")
    except ModuleNotFoundError as exc:
        raise ImproperlyConfigured(
            "python-oracledb is required for OracleAdapter. "
            "Install it in the runtime environment before using Oracle data adapters."
        ) from exc
    return cast(_OracleDriver, driver_module)


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} is required for OracleAdapter configuration."
        )
    return value


def _validate_oracle_username(username: str) -> str:
    candidate = username.strip()
    if not _ORACLE_USERNAME_RE.fullmatch(candidate):
        raise ImproperlyConfigured(
            "ORACLE_USERNAME must match ^[A-Za-z][A-Za-z0-9_#$]{0,127}$ for a strict allowlist."
        )

    if candidate.upper() in _DISALLOWED_ORACLE_USERNAMES:
        raise ImproperlyConfigured(
            "ORACLE_USERNAME must be a least-privilege application account, not a privileged Oracle system account."
        )

    return candidate


def _is_tls_dsn(dsn: str) -> bool:
    candidate = dsn.strip()
    if candidate.lower().startswith("tcps://"):
        return True
    return _TLS_DSN_PROTOCOL_RE.search(candidate) is not None


def _validate_oracle_dsn(dsn: str, *, require_tls: bool) -> str:
    candidate = dsn.strip()
    if require_tls and not _is_tls_dsn(candidate):
        raise ImproperlyConfigured(
            "ORACLE_DSN must use TLS/TCPS when ORACLE_REQUIRE_TLS is enabled."
        )
    return candidate


def _int_env(
    env: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer.") from exc

    if value < minimum:
        raise ImproperlyConfigured(f"{name} must be >= {minimum}.")
    return value


def _float_env(
    env: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float,
) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default

    try:
        value = float(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a floating-point number.") from exc

    if value < minimum:
        raise ImproperlyConfigured(f"{name} must be >= {minimum}.")
    return value


def _bool_env(
    env: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default

    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False

    raise ImproperlyConfigured(
        f"{name} must be a boolean string: 1/0, true/false, yes/no, on/off."
    )


def _query_id(statement: str) -> str:
    digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    return digest[:12]


def _canonicalize_query_params(params: OracleQueryParams) -> object:
    if params is None:
        return None
    if isinstance(params, Mapping):
        return {str(key): params[key] for key in sorted(params, key=str)}
    return [item for item in params]


def _cache_identifier(statement: str, params: OracleQueryParams) -> str:
    payload = {
        "statement": statement,
        "params": _canonicalize_query_params(params),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return _query_id(encoded)


def _validate_param_value(value: object) -> None:
    allowed_types = (
        str,
        int,
        float,
        bool,
        bytes,
        bytearray,
        memoryview,
        date,
        datetime,
        Decimal,
        type(None),
    )
    if not isinstance(value, allowed_types):
        raise ValueError(
            "Oracle query parameters must be scalar values (str/int/float/bool/date/datetime/Decimal/bytes) or None."
        )

    if isinstance(value, str) and len(value) > _MAX_STRING_PARAM_LENGTH:
        raise ValueError(
            f"Oracle string parameter length exceeds {_MAX_STRING_PARAM_LENGTH} characters."
        )

    if (
        isinstance(value, (bytes, bytearray, memoryview))
        and len(value) > _MAX_BINARY_PARAM_LENGTH
    ):
        raise ValueError(
            f"Oracle binary parameter length exceeds {_MAX_BINARY_PARAM_LENGTH} bytes."
        )


def _validate_query_params(params: OracleQueryParams) -> OracleQueryParams:
    if params is None:
        return None

    if isinstance(params, Mapping):
        if len(params) > _MAX_QUERY_PARAMS:
            raise ValueError(
                f"Oracle query parameters exceed the maximum of {_MAX_QUERY_PARAMS}."
            )

        normalized: dict[str, object] = {}
        for key, value in params.items():
            if not isinstance(key, str) or not _BIND_PARAM_NAME_RE.fullmatch(key):
                raise ValueError(
                    "Oracle named bind parameters must match ^[A-Za-z_][A-Za-z0-9_]{0,63}$."
                )
            _validate_param_value(value)
            normalized[key] = value
        return normalized

    if isinstance(params, (str, bytes, bytearray)):
        raise ValueError(
            "Oracle positional bind parameters must be a sequence of values, not a raw string/bytes object."
        )

    if isinstance(params, Sequence):
        normalized_seq = list(params)
        if len(normalized_seq) > _MAX_QUERY_PARAMS:
            raise ValueError(
                f"Oracle query parameters exceed the maximum of {_MAX_QUERY_PARAMS}."
            )
        for value in normalized_seq:
            _validate_param_value(value)
        return normalized_seq

    raise ValueError("Oracle query parameters must be a mapping, a sequence, or None.")


def _extract_oracle_error_code(exc: Exception) -> int | None:
    details = exc.args[0] if exc.args else exc
    code = getattr(details, "code", None)
    if isinstance(code, int):
        return code

    match = _ORACLE_ERROR_CODE_RE.search(str(details))
    if match is None:
        return None
    return int(match.group(1))


def _is_read_query(sql: str) -> bool:
    token = sql.split(None, 1)[0].upper()
    return token in {"SELECT", "WITH"}


def _validate_read_query(sql: str) -> str:
    if not isinstance(sql, str):
        raise ValueError("SQL statement must be a non-empty string.")

    statement = sql.strip()
    if not statement:
        raise ValueError("SQL statement must be a non-empty string.")
    if len(statement) > _MAX_SQL_LENGTH:
        raise ValueError(
            f"SQL statement exceeds the maximum length of {_MAX_SQL_LENGTH} characters."
        )
    if "\x00" in statement:
        raise ValueError("SQL statement contains invalid NUL characters.")
    if ";" in statement:
        raise ValueError(
            "OracleAdapter accepts exactly one SQL statement and does not allow statement delimiters (;)."
        )
    if not _is_read_query(statement):
        raise ValueError(
            "OracleAdapter only supports read-only SELECT/WITH statements. "
            "Use dedicated write adapters for INSERT/UPDATE/DELETE operations."
        )
    return statement


def _column_names(description: Sequence[Sequence[object]] | None) -> list[str]:
    if not description:
        return []

    columns: list[str] = []
    for index, column in enumerate(description, start=1):
        raw_name = column[0] if column else None
        if isinstance(raw_name, str) and raw_name.strip():
            columns.append(raw_name.strip().lower())
        else:
            columns.append(f"column_{index}")
    return columns


def _row_to_dict(columns: Sequence[str], row: Sequence[object]) -> OracleRow:
    return {column: value for column, value in zip(columns, row)}


@dataclass(frozen=True, slots=True)
class OracleAdapterConfig:
    """Runtime configuration for OracleAdapter."""

    username: str
    password: str
    dsn: str
    pool_min_connections: int = 4
    pool_max_connections: int = 30
    pool_increment: int = 2
    pool_timeout_seconds: int = 120
    pool_wait_timeout_seconds: int = 30
    max_lifetime_session_seconds: int = 3600
    statement_cache_size: int = 50
    arraysize: int = 200
    prefetch_rows: int = 200
    call_timeout_ms: int = 30000
    max_retry_attempts: int = 3
    retry_backoff_seconds: float = 0.25
    cache_enabled: bool = False
    cache_ttl_seconds: int = 30
    require_tls: bool = True
    ssl_server_dn_match: bool = True

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "OracleAdapterConfig":
        """Build adapter config from environment variables.

        Required:
        - ORACLE_USERNAME
        - ORACLE_PASSWORD
        - ORACLE_DSN
        """

        environment = env if env is not None else os.environ
        require_tls = _bool_env(environment, "ORACLE_REQUIRE_TLS", default=True)
        return cls(
            username=_validate_oracle_username(
                _required_env(environment, "ORACLE_USERNAME")
            ),
            password=_required_env(environment, "ORACLE_PASSWORD"),
            dsn=_validate_oracle_dsn(
                _required_env(environment, "ORACLE_DSN"),
                require_tls=require_tls,
            ),
            pool_min_connections=_int_env(
                environment, "ORACLE_POOL_MIN_CONNECTIONS", default=4, minimum=1
            ),
            pool_max_connections=_int_env(
                environment, "ORACLE_POOL_MAX_CONNECTIONS", default=30, minimum=1
            ),
            pool_increment=_int_env(
                environment, "ORACLE_POOL_INCREMENT", default=2, minimum=1
            ),
            pool_timeout_seconds=_int_env(
                environment, "ORACLE_POOL_TIMEOUT_SECONDS", default=120, minimum=1
            ),
            pool_wait_timeout_seconds=_int_env(
                environment, "ORACLE_POOL_WAIT_TIMEOUT_SECONDS", default=30, minimum=1
            ),
            max_lifetime_session_seconds=_int_env(
                environment,
                "ORACLE_MAX_LIFETIME_SESSION_SECONDS",
                default=3600,
                minimum=1,
            ),
            statement_cache_size=_int_env(
                environment, "ORACLE_STATEMENT_CACHE_SIZE", default=50, minimum=0
            ),
            arraysize=_int_env(environment, "ORACLE_ARRAYSIZE", default=200, minimum=1),
            prefetch_rows=_int_env(
                environment, "ORACLE_PREFETCH_ROWS", default=200, minimum=1
            ),
            call_timeout_ms=_int_env(
                environment, "ORACLE_CALL_TIMEOUT_MS", default=30000, minimum=1
            ),
            max_retry_attempts=_int_env(
                environment, "ORACLE_MAX_RETRY_ATTEMPTS", default=3, minimum=1
            ),
            retry_backoff_seconds=_float_env(
                environment,
                "ORACLE_RETRY_BACKOFF_SECONDS",
                default=0.25,
                minimum=0.0,
            ),
            cache_enabled=_bool_env(environment, "ORACLE_CACHE_ENABLED", default=False),
            cache_ttl_seconds=_int_env(
                environment, "ORACLE_CACHE_TTL_SECONDS", default=30, minimum=1
            ),
            require_tls=require_tls,
            ssl_server_dn_match=_bool_env(
                environment, "ORACLE_SSL_SERVER_DN_MATCH", default=True
            ),
        )


_T = TypeVar("_T")


class OracleAdapter:
    """Reusable Oracle data adapter intended for the service layer.

    The adapter is read-only by design so BFF services can safely execute
    parameterized SELECT/WITH queries and receive native Python objects.
    """

    def __init__(
        self,
        config: OracleAdapterConfig,
        *,
        driver: _OracleDriver | None = None,
    ) -> None:
        self.config = config
        self._driver = driver if driver is not None else _load_oracle_driver()
        _validate_oracle_username(self.config.username)
        _validate_oracle_dsn(self.config.dsn, require_tls=self.config.require_tls)

        pool_kwargs: dict[str, object] = {
            "user": self.config.username,
            "password": self.config.password,
            "dsn": self.config.dsn,
            "min": self.config.pool_min_connections,
            "max": self.config.pool_max_connections,
            "increment": self.config.pool_increment,
            "timeout": self.config.pool_timeout_seconds,
            "wait_timeout": self.config.pool_wait_timeout_seconds,
            "max_lifetime_session": self.config.max_lifetime_session_seconds,
            "stmtcachesize": self.config.statement_cache_size,
        }
        if self.config.require_tls:
            pool_kwargs["ssl_server_dn_match"] = self.config.ssl_server_dn_match

        getmode_wait = getattr(self._driver, "POOL_GETMODE_WAIT", None)
        if getmode_wait is not None:
            pool_kwargs["getmode"] = getmode_wait

        self._pool = self._driver.create_pool(**pool_kwargs)

    def fetch_all(
        self,
        sql: str,
        params: OracleQueryParams = None,
    ) -> list[OracleRow]:
        """Execute a read-only query and return all rows as dictionaries."""
        statement = _validate_read_query(sql)
        validated_params = _validate_query_params(params)
        statement_id = _query_id(statement)
        started = time.perf_counter()
        cache_key = self._build_cache_key(
            operation="fetch_all", statement=statement, params=validated_params
        )

        if cache_key is not None:
            cached_rows = self._cache_get(cache_key)
            if cached_rows is not _CACHE_MISS:
                rows = cast(list[OracleRow], deepcopy(cached_rows))
                self._log_query_success(
                    statement_id=statement_id,
                    row_count=len(rows),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    cache_hit=True,
                    cache_key=cache_key,
                )
                return rows

        def _operation() -> list[OracleRow]:
            with self._pool.acquire() as connection:
                connection.call_timeout = self.config.call_timeout_ms
                with connection.cursor() as cursor:
                    cursor.arraysize = self.config.arraysize
                    cursor.prefetchrows = self.config.prefetch_rows
                    if validated_params is None:
                        cursor.execute(statement)
                    else:
                        cursor.execute(statement, validated_params)

                    columns = _column_names(cursor.description)
                    return [_row_to_dict(columns, row) for row in cursor.fetchall()]

        rows = self._run_with_retry(_operation, statement_id=statement_id)
        if cache_key is not None:
            self._cache_set(cache_key, rows)
        self._log_query_success(
            statement_id=statement_id,
            row_count=len(rows),
            duration_ms=(time.perf_counter() - started) * 1000,
            cache_hit=False,
            cache_key=cache_key,
        )
        return rows

    def fetch_one(
        self,
        sql: str,
        params: OracleQueryParams = None,
    ) -> OracleRow | None:
        """Execute a read-only query and return the first row, if any."""
        statement = _validate_read_query(sql)
        validated_params = _validate_query_params(params)
        statement_id = _query_id(statement)
        started = time.perf_counter()
        cache_key = self._build_cache_key(
            operation="fetch_one", statement=statement, params=validated_params
        )

        if cache_key is not None:
            cached_row = self._cache_get(cache_key)
            if cached_row is not _CACHE_MISS:
                row = cast(OracleRow | None, deepcopy(cached_row))
                self._log_query_success(
                    statement_id=statement_id,
                    row_count=0 if row is None else 1,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    cache_hit=True,
                    cache_key=cache_key,
                )
                return row

        def _operation() -> OracleRow | None:
            with self._pool.acquire() as connection:
                connection.call_timeout = self.config.call_timeout_ms
                with connection.cursor() as cursor:
                    cursor.arraysize = self.config.arraysize
                    cursor.prefetchrows = self.config.prefetch_rows
                    if validated_params is None:
                        cursor.execute(statement)
                    else:
                        cursor.execute(statement, validated_params)

                    row = cursor.fetchone()
                    if row is None:
                        return None

                    columns = _column_names(cursor.description)
                    return _row_to_dict(columns, row)

        row = self._run_with_retry(_operation, statement_id=statement_id)
        if cache_key is not None:
            self._cache_set(cache_key, row)
        self._log_query_success(
            statement_id=statement_id,
            row_count=0 if row is None else 1,
            duration_ms=(time.perf_counter() - started) * 1000,
            cache_hit=False,
            cache_key=cache_key,
        )
        return row

    def close(self) -> None:
        """Close the Oracle connection pool."""
        self._pool.close(force=True)

    async def fetch_all_async(
        self,
        sql: str,
        params: OracleQueryParams = None,
    ) -> list[OracleRow]:
        """Async wrapper for fetch_all suitable for async Django/ASGI views."""
        return await sync_to_async(self.fetch_all, thread_sensitive=False)(sql, params)

    async def fetch_one_async(
        self,
        sql: str,
        params: OracleQueryParams = None,
    ) -> OracleRow | None:
        """Async wrapper for fetch_one suitable for async Django/ASGI views."""
        return await sync_to_async(self.fetch_one, thread_sensitive=False)(sql, params)

    async def close_async(self) -> None:
        """Async wrapper for close suitable for async shutdown hooks."""
        await sync_to_async(self.close, thread_sensitive=False)()

    def _run_with_retry(
        self,
        operation: Callable[[], _T],
        *,
        statement_id: str,
    ) -> _T:
        for attempt in range(1, self.config.max_retry_attempts + 1):
            try:
                return operation()
            except self._driver.DatabaseError as exc:
                error_code = _extract_oracle_error_code(exc)
                retryable = (
                    error_code is not None
                    and error_code in _TRANSIENT_ORACLE_ERROR_CODES
                    and attempt < self.config.max_retry_attempts
                )
                if not retryable:
                    logger.exception(
                        "oracle query failed",
                        extra=build_security_event_fields(
                            None,
                            event_type="ORACLE_QUERY_FAILURE",
                            action_attempted="execute oracle read query",
                            result="failure",
                            resource_accessed="oracle:read",
                            request_id=request_id_var.get(),
                            status_code=500,
                            exception_type=exc.__class__.__name__,
                            oracle_query_id=statement_id,
                            oracle_error_code=error_code,
                            oracle_attempt=attempt,
                        ),
                    )
                    raise

                sleep_seconds = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "transient oracle error; retrying query",
                    extra=build_security_event_fields(
                        None,
                        event_type="ORACLE_QUERY_RETRY",
                        action_attempted="execute oracle read query",
                        result="failure",
                        resource_accessed="oracle:read",
                        request_id=request_id_var.get(),
                        exception_type=exc.__class__.__name__,
                        oracle_query_id=statement_id,
                        oracle_error_code=error_code,
                        oracle_attempt=attempt,
                        oracle_sleep_seconds=round(sleep_seconds, 3),
                    ),
                )
                time.sleep(sleep_seconds)
            except Exception as exc:
                logger.exception(
                    "oracle query failed with non-driver exception",
                    extra=build_security_event_fields(
                        None,
                        event_type="ORACLE_QUERY_FAILURE",
                        action_attempted="execute oracle read query",
                        result="failure",
                        resource_accessed="oracle:read",
                        request_id=request_id_var.get(),
                        status_code=500,
                        exception_type=exc.__class__.__name__,
                        oracle_query_id=statement_id,
                        oracle_attempt=attempt,
                    ),
                )
                raise

        raise RuntimeError(  # pragma: no cover - defensive loop guard
            "Oracle retry loop exited without returning or raising."
        )

    def _build_cache_key(
        self,
        *,
        operation: str,
        statement: str,
        params: OracleQueryParams,
    ) -> str | None:
        if not self.config.cache_enabled:
            return None
        identifier = _cache_identifier(statement, params)
        return adapter_key("oracle", operation, identifier)

    def _cache_get(self, cache_key: str) -> object:
        try:
            return cache.get(cache_key, _CACHE_MISS)
        except Exception as exc:  # pragma: no cover - defensive fail-open guard
            logger.warning(
                "oracle cache lookup failed",
                extra=build_security_event_fields(
                    None,
                    event_type="ORACLE_CACHE_FAILURE",
                    action_attempted="read adapter cache",
                    result="failure",
                    resource_accessed="oracle:cache",
                    request_id=request_id_var.get(),
                    exception_type=exc.__class__.__name__,
                    oracle_cache_key=cache_key,
                ),
            )
            return _CACHE_MISS

    def _cache_set(self, cache_key: str, value: object) -> None:
        try:
            cache.set(
                cache_key,
                deepcopy(value),
                timeout=self.config.cache_ttl_seconds,
            )
        except Exception as exc:  # pragma: no cover - defensive fail-open guard
            logger.warning(
                "oracle cache write failed",
                extra=build_security_event_fields(
                    None,
                    event_type="ORACLE_CACHE_FAILURE",
                    action_attempted="write adapter cache",
                    result="failure",
                    resource_accessed="oracle:cache",
                    request_id=request_id_var.get(),
                    exception_type=exc.__class__.__name__,
                    oracle_cache_key=cache_key,
                    oracle_cache_ttl_seconds=self.config.cache_ttl_seconds,
                ),
            )

    def _log_query_success(
        self,
        *,
        statement_id: str,
        row_count: int,
        duration_ms: float,
        cache_hit: bool,
        cache_key: str | None,
    ) -> None:
        logger.info(
            "oracle query completed",
            extra=build_security_event_fields(
                None,
                event_type="ORACLE_QUERY_SUCCESS",
                action_attempted="execute oracle read query",
                result="success",
                resource_accessed="oracle:read",
                request_id=request_id_var.get(),
                duration_ms=duration_ms,
                oracle_query_id=statement_id,
                oracle_row_count=row_count,
                oracle_cache_hit=cache_hit if cache_key is not None else None,
                oracle_cache_key=cache_key,
                oracle_cache_ttl_seconds=self.config.cache_ttl_seconds
                if cache_key is not None
                else None,
            ),
        )


def create_oracle_adapter_from_env(
    *,
    driver: _OracleDriver | None = None,
) -> OracleAdapter:
    """Create a reusable OracleAdapter using ORACLE_* environment variables."""
    return OracleAdapter(OracleAdapterConfig.from_env(), driver=driver)
