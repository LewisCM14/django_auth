# Implementation Plan

*Step-by-step implementation of the logging, exception handling, and caching capabilities described in [spec.md](/docs/spec.md). Each step is delivered individually per the [CONTRIBUTING.md](/docs/CONTRIBUTING.md) workflow. Implementation steps and verification-test steps are separated — the implementation step establishes the production code, immediately followed by a test step that verifies behaviour and enforces 100% coverage. The full quality gate (tests, coverage, mypy, ruff) is enforced at the test step; the implementation step must pass mypy and ruff but may have uncovered lines until the test step lands.*

**Baseline:** 66 passing tests, 100% coverage, mypy clean, ruff clean.

---

## Phase 1 — Structured Logging

Logging is implemented first because the exception handler and caching improvements both emit log messages. Getting the logging infrastructure in place means subsequent phases can verify their logging behaviour in tests.

### Step 01: Add `django-redis` dependency to manifests

**Type:** Config

Add `django-redis` to `pyproject.toml` (under `[project.dependencies]`) and to `environment.yml` (under `dependencies`, `conda-forge` channel). This unblocks the caching steps later but is done now so there is only one dependency update step.

**Files changed:**
- `pyproject.toml`
- `environment.yml`

**Acceptance criteria:**
- `uv sync` completes without error.
- `uv run python -c "import django_redis"` succeeds.
- No test, mypy, or ruff regressions.

---

### Step 02: Implement request-ID context variable and logging filter

**Type:** Implementation

Refactor `api/middleware/request_id.py` to:

1. Define a module-level `contextvars.ContextVar[str]` named `request_id_var` (default `"-"`).
2. In `process_request`, after generating the UUID, store it in `request_id_var` (in addition to the existing `request.request_id` attribute).
3. Add a `RequestIdFilter(logging.Filter)` class that reads `request_id_var` and injects `request_id` into every log record.
4. In `process_response`, reset `request_id_var` to `"-"` after attaching the header (cleanup).

No logging configuration yet — that comes in step 04. This step only adds the context variable and filter class.

**Files changed:**
- `api/middleware/request_id.py`

**Acceptance criteria:**
- Existing 4 request-ID tests still pass (context variable is additive).
- `RequestIdFilter` class exists and is importable.
- `request_id_var` is importable from `api.middleware.request_id`.
- mypy clean, ruff clean (100% coverage restored at step 03 when tests land).

---

### Step 03: Tests for request-ID context variable and logging filter (Red)

**Type:** Tests

Write tests in `tests/api/middleware/test_request_id.py`:

1. `test_request_id_var_set_during_request` — Call a view via the test client, confirm `request_id_var` was set during the request lifecycle (use a mock view that captures the value).
2. `test_request_id_var_reset_after_response` — After a request completes, `request_id_var.get()` returns `"-"`.
3. `test_request_id_filter_injects_request_id` — Create a `RequestIdFilter`, set `request_id_var` to a known value, create a `LogRecord`, call `filter()`, and assert `record.request_id` equals the known value.
4. `test_request_id_filter_uses_default_when_no_context` — With `request_id_var` at default, filter injects `"-"`.

**Files changed:**
- `tests/api/middleware/test_request_id.py`

**Acceptance criteria:**
- New tests pass (Green, since step 02 already implemented the code).
- 100% coverage on `api/middleware/request_id.py`.

---

### Step 04: Add `LOGGING` configuration to settings

**Type:** Implementation

Create `config/logging.py` with a `JsonFormatter(logging.Formatter)` class that emits single-line JSON: `{"timestamp", "level", "logger", "request_id", "message"}`. Keeping the class in its own module (rather than `settings.py`) allows it to be tested in isolation without triggering settings validation guards.

Add to `config/settings.py`:

1. A `LOGGING` dict using `dictConfig` format:
   - **Filters:** `request_id` filter using `api.middleware.request_id.RequestIdFilter`.
   - **Formatters:** `json` (references `config.logging.JsonFormatter` by dotted path), `text` (uses format string `[{levelname}] {request_id} {message}`).
   - **Handlers:** `console` handler (`StreamHandler` to stderr), using `json` or `text` formatter based on `LOG_FORMAT` env var (default `text`).
   - **Loggers:** `api` logger at `DEBUG` (dev) or `INFO` (prod); `django` logger at `INFO` (dev) or `WARNING` (prod).
   - **Root:** Level from `LOG_LEVEL` env var (default `DEBUG` in dev, `WARNING` in prod).
2. Read `LOG_FORMAT` and `LOG_LEVEL` environment variables.

**Files changed:**
- `config/logging.py` (new file)
- `config/settings.py`

**Acceptance criteria:**
- `uv run python -c "from config.settings import LOGGING; print(LOGGING)"` outputs valid dict.
- Application starts without error (`uv run python manage.py check`).
- mypy clean, ruff clean.
- Existing tests unaffected (no log output contamination — tests capture logging or use `text` format).

---

### Step 05: Tests for logging configuration (Red → Green)

**Type:** Tests

Write tests in `tests/config/test_settings.py` (add to existing file or create if it doesn't exist):

1. `test_logging_config_has_request_id_filter` — Assert `LOGGING["filters"]` contains `request_id` key.
2. `test_logging_config_console_handler_exists` — Assert `LOGGING["handlers"]["console"]` is configured.
3. `test_json_formatter_output_shape` — Import `JsonFormatter` from `config.logging`, format a log record, parse the output as JSON, verify keys `timestamp`, `level`, `logger`, `request_id`, `message` are present.
4. `test_json_formatter_includes_request_id_from_record` — Set `request_id` on a log record extra, format it, verify the value appears in the JSON output.

**Files changed:**
- `tests/config/test_settings.py`
- `tests/config/test_logging.py` (new file for `JsonFormatter` tests)

**Acceptance criteria:**
- All new tests pass.
- 100% coverage maintained.

---

### Step 06: Add request/response access logging to `RequestIdMiddleware`

**Type:** Implementation

In `api/middleware/request_id.py`:

1. Add `import logging` and `import time` at the top.
2. In `process_request`, record `request._start_time = time.monotonic()`.
3. In `process_response`, compute duration, log at `INFO` level: `logger.info` with message containing method, path, status code, duration_ms, and username (from `request.user` if authenticated, else `"anonymous"`).

The log record automatically gets `request_id` injected by the `RequestIdFilter` configured in step 04.

**Files changed:**
- `api/middleware/request_id.py`

**Acceptance criteria:**
- Running `uv run pytest` shows no log noise (pytest captures logging by default).
- All existing tests pass.
- mypy clean, ruff clean.

---

### Step 07: Tests for access logging (Red → Green)

**Type:** Tests

Add tests to `tests/api/middleware/test_request_id.py`:

1. `test_access_log_emitted_on_response` — Make a request via the test client, use `caplog` to assert an `INFO` log was emitted containing the method, path, and status code.
2. `test_access_log_includes_duration` — Assert the log record contains `duration_ms` as a non-negative number.
3. `test_access_log_includes_username_when_authenticated` — Request as an authenticated user, assert the log contains the username.
4. `test_access_log_shows_anonymous_when_unauthenticated` — Request to a public endpoint without auth, assert log contains `"anonymous"`.

**Files changed:**
- `tests/api/middleware/test_request_id.py`

**Acceptance criteria:**
- All tests pass.
- 100% coverage on `api/middleware/request_id.py`.

---

### Step 08: Add audit logging to authorization middleware

**Type:** Implementation

In `api/middleware/authorization.py`:

1. Add `import logging` and create `logger = logging.getLogger(__name__)`.
2. In the `except AuthenticationFailed` block, add `logger.warning(...)` with the requested path and reason before returning the 401 response.
3. In the `except PermissionDenied` block, add `logger.warning(...)` with the username, requested path, and reason before returning the 403 response.

**Files changed:**
- `api/middleware/authorization.py`

**Acceptance criteria:**
- All existing authorization tests pass.
- mypy clean, ruff clean.

---

### Step 09: Tests for authorization audit logging (Red → Green)

**Type:** Tests

Add tests to `tests/api/middleware/test_authorization.py`:

1. `test_401_response_logs_warning` — Trigger a 401 via unauthenticated request to a roles-protected view, assert `caplog` contains a `WARNING` record with the path.
2. `test_403_response_logs_warning_with_username` — Trigger a 403 via an authenticated user without matching roles, assert `caplog` contains a `WARNING` record with the username and path.

**Files changed:**
- `tests/api/middleware/test_authorization.py`

**Acceptance criteria:**
- All tests pass.
- 100% coverage maintained on `api/middleware/authorization.py`.

---

## Phase 2 — Exception Handling

The DRF exception handler builds on the logging infrastructure from Phase 1. It uses the request-ID context variable and emits log messages through the configured pipeline.

### Step 10: Implement custom DRF exception handler

**Type:** Implementation

Create `api/exceptions.py`:

1. Define `api_exception_handler(exc, context)` function.
2. Delegate to DRF's `rest_framework.views.exception_handler(exc, context)` first.
3. If DRF returns a response:
   - Add `request_id` to `response.data` (read from `request_id_var` or `request.request_id`).
   - Return the enriched response.
4. If DRF returns `None` (unhandled exception):
   - Log the full traceback at `ERROR` level via `logger.exception(...)`.
   - Return `JsonResponse({"detail": "An unexpected error occurred.", "request_id": ...}, status=500)`.

**Files changed:**
- `api/exceptions.py` (new file)

**Acceptance criteria:**
- `api_exception_handler` is importable.
- mypy clean, ruff clean.
- Not yet wired into settings (step 12).

---

### Step 11: Tests for custom exception handler (Red → Green)

**Type:** Tests

Create `tests/api/test_exceptions.py`:

1. `test_drf_api_exception_returns_detail_and_request_id` — Call handler with a `NotFound` exception, assert response has `detail` and `request_id` fields, status 404.
2. `test_authentication_failed_returns_401_with_request_id` — Call handler with `AuthenticationFailed`, assert 401 with both fields.
3. `test_permission_denied_returns_403_with_request_id` — Call handler with `PermissionDenied`, assert 403.
4. `test_validation_error_preserves_field_errors_and_adds_request_id` — Call handler with a DRF `ValidationError` carrying field-level errors, assert `detail` contains the field errors and `request_id` is present.
5. `test_unhandled_exception_returns_500_with_request_id` — Call handler with a `RuntimeError`, assert 500, `detail` is generic message, `request_id` present.
6. `test_unhandled_exception_logs_traceback` — Call handler with a `RuntimeError`, use `caplog` to assert `ERROR` log was emitted with traceback content.

**Files changed:**
- `tests/api/test_exceptions.py` (new file)

**Acceptance criteria:**
- All tests pass.
- 100% coverage on `api/exceptions.py`.

---

### Step 12: Wire exception handler into DRF settings

**Type:** Implementation

Update `config/settings.py`:

1. Add `"EXCEPTION_HANDLER": "api.exceptions.api_exception_handler"` to the `REST_FRAMEWORK` dict.

**Files changed:**
- `config/settings.py`

**Acceptance criteria:**
- All existing endpoint tests still pass (verify the enriched response shape doesn't break assertions — existing tests check `detail` but not `request_id`).
- `uv run python manage.py check` clean.
- mypy clean, ruff clean.

---

### Step 13: Update authorization middleware to include `request_id` in error responses

**Type:** Implementation

Update `api/middleware/authorization.py`:

1. In the `except AuthenticationFailed` block, add `"request_id"` to the `JsonResponse` data, read from `request_id_var`.
2. In the `except PermissionDenied` block, same.

This aligns the middleware's error responses with the DRF exception handler's contract (both now include `request_id`).

**Files changed:**
- `api/middleware/authorization.py`

**Acceptance criteria:**
- All existing authorization tests still pass (may need minor assertion updates to account for the new `request_id` field).
- Error responses from middleware now include `request_id`.
- mypy clean, ruff clean.

---

### Step 14: Tests for updated middleware error responses (Red → Green)

**Type:** Tests

Update relevant tests in `tests/api/middleware/test_authorization.py` and integration tests:

1. `test_401_response_includes_request_id` — Assert the 401 JSON response body contains a `request_id` key.
2. `test_403_response_includes_request_id` — Same for 403.
3. Update existing 401/403 body assertions if they use exact dict match (add `request_id` to expected shape or use `assert "detail" in body` pattern).

**Files changed:**
- `tests/api/middleware/test_authorization.py`
- Any integration test files that assert exact body shape on 401/403.

**Acceptance criteria:**
- All tests pass.
- 100% coverage maintained.

---

## Phase 3 — Caching

Caching builds on the dependency added in step 01 (`django-redis`). The cache is used for application-level data (adapter responses, service-layer results, view responses) — **not** for LDAP group membership, which is queried fresh on every `@authz_roles` request to ensure AD changes take immediate effect.

### Step 15: Implement environment-aware cache backend configuration

**Type:** Implementation

Update `config/settings.py`:

1. Read `CACHE_BACKEND` env var (default `"locmem"`).
2. Read `REDIS_URL` env var.
3. If `CACHE_BACKEND == "redis"`, configure:
   ```python
   CACHES = {
       "default": {
           "BACKEND": "django_redis.cache.RedisCache",
           "LOCATION": REDIS_URL,
           "OPTIONS": {
               "CLIENT_CLASS": "django_redis.client.DefaultClient",
           },
       }
   }
   ```
4. Otherwise, keep the existing `LocMemCache` configuration.
5. Validate: if `CACHE_BACKEND == "redis"` and `REDIS_URL` is empty, raise `ImproperlyConfigured`.

**Files changed:**
- `config/settings.py`

**Acceptance criteria:**
- Default behaviour unchanged (tests use `LocMemCache`).
- `CACHE_BACKEND=redis REDIS_URL=redis://localhost:6379/0 uv run python -c "from django.conf import settings; print(settings.CACHES)"` shows Redis backend.
- Missing `REDIS_URL` with `CACHE_BACKEND=redis` raises `ImproperlyConfigured`.
- mypy clean, ruff clean.
- All existing tests pass (they default to `locmem`).

---

### Step 16: Tests for cache backend configuration (Red → Green)

**Type:** Tests

Add tests to `tests/config/test_settings.py`:

1. `test_default_cache_backend_is_locmem` — With no env vars, assert `CACHES["default"]["BACKEND"]` contains `LocMemCache`.
2. `test_redis_cache_backend_when_configured` — Monkeypatch `CACHE_BACKEND=redis` and `REDIS_URL=redis://localhost:6379/0`, re-import/re-evaluate the relevant settings logic, assert the backend is `RedisCache`.
3. `test_redis_backend_without_url_raises_error` — Monkeypatch `CACHE_BACKEND=redis` with no `REDIS_URL`, assert `ImproperlyConfigured` is raised.

**Files changed:**
- `tests/config/test_settings.py`

**Acceptance criteria:**
- All tests pass.
- Coverage maintained.

---

### Step 17: Add `Cache-Control` headers to existing views

**Type:** Implementation

Update existing views with appropriate HTTP cache headers:

1. `api/views/health.py` — Add `@cache_control(public=True, max_age=5)` to `HealthView`. Health probes benefit from a short cache.
2. `api/views/user.py` — Add `Cache-Control: private, no-cache` header to the `GET` response. User-specific data should not be cached by shared proxies but browsers can revalidate.
3. `api/views/docs.py` — No change (drf-spectacular controls its own headers).

**Files changed:**
- `api/views/health.py`
- `api/views/user.py`

**Acceptance criteria:**
- `GET /api/health/` response includes `Cache-Control: public, max-age=5`.
- `GET /api/user/` response includes `Cache-Control: private, no-cache`.
- All existing tests pass.
- mypy clean, ruff clean.

---

### Step 18: Tests for cache headers (Red → Green)

**Type:** Tests

Add tests:

1. In `tests/api/views/test_health.py`: `test_health_response_has_public_cache_header` — Assert `Cache-Control` header contains `public` and `max-age=5`.
2. In `tests/api/views/test_user.py`: `test_user_response_has_private_cache_header` — Assert `Cache-Control` header contains `private` and `no-cache`.

**Files changed:**
- `tests/api/views/test_health.py`
- `tests/api/views/test_user.py`

**Acceptance criteria:**
- All tests pass.
- 100% coverage maintained.

---

## Phase 4 — Cleanup & Validation

### Step 19: Update `.env.example` with new environment variables

**Type:** Config

Add the new environment variables to `.env.example` with documentation comments:

```
# Logging
LOG_FORMAT=text       # text (dev) or json (production)
LOG_LEVEL=DEBUG       # Python log level (DEBUG, INFO, WARNING, ERROR)

# Cache
CACHE_BACKEND=locmem  # locmem (dev) or redis (production)
REDIS_URL=            # Required when CACHE_BACKEND=redis
```

**Files changed:**
- `.env.example`

**Acceptance criteria:**
- `.env.example` documents all environment variables referenced in `config/settings.py`.

---

### Step 20: Final validation

**Type:** Validation

Run the full quality gate suite and confirm no regressions:

| Check | Command | Expected |
|-------|---------|----------|
| Tests pass | `uv run pytest -q` | All green |
| Coverage | `uv run pytest` (coverage in addopts) | 100% |
| Type checking | `uv run mypy api config` | 0 errors |
| Linting | `uv run ruff check .` | All checks passed |
| Django check | `uv run python manage.py check` | 0 issues |

**Acceptance criteria:**
- All five checks pass.
- Test count has increased from 66 baseline (new tests for logging, exceptions, caching).
- No `# type: ignore` annotations without explanatory comments.
- `spec.md` accurately describes the implemented behaviour.