# Implementation Plan

*Walking skeleton approach with TDD. Each step produces a passing test suite and a reviewable diff. No step is started until the previous step is approved.*

*Refer to [CONTRIBUTING.md](/docs/CONTRIBUTING.md) for the code delivery and review workflow.*

---

## Phase 1 — Skeleton: Project bootstrap, config, and first green test

The goal of this phase is to have a runnable Django project with a single passing test, confirming the toolchain (uv, Django, DRF, pytest, mypy) works end-to-end before any application logic is written.

### Step 1: Environment & dependency manifests

Create `pyproject.toml` as the primary dependency manifest (used locally with `uv`) and `environment.yml` for production Anaconda deployment on Windows. Both describe the same dependency set.

**Files created:**
- `backend/pyproject.toml`
- `backend/environment.yml`

**Packages:**
- `python=3.14`
- `django>=6.0.0`
- `djangorestframework>=3.0.0`
- `drf-spectacular`
- `django-cors-headers`
- `ldap3>=2.9`
- `python-dotenv`
- `pytest`
- `pytest-django`
- `pytest-mock`
- `pytest-cov`
- `mypy`
- `django-stubs`
- `djangorestframework-stubs`

**Acceptance criteria:**
- `uv sync` succeeds locally (WSL).
- `python --version` outputs `3.14.x`.
- `uv pip list` shows all packages present.
- `environment.yml` lists equivalent packages from `conda-forge` for Windows production deployment.

---

### Step 2: Django project scaffolding

Create the minimal Django project structure with `config/` as the project package. No application logic yet — just enough to get `manage.py runserver` to start.

**Files created:**
- `backend/manage.py`
- `backend/config/__init__.py`
- `backend/config/settings.py`
- `backend/config/urls.py`
- `backend/config/wsgi.py`
- `backend/.env.example`
- `backend/.env` (gitignored, dev defaults)
- `backend/.gitignore`

**`settings.py` must include:**
- `python-dotenv` loading in `settings.py` (not `manage.py`).
- `AUTH_MODE` read from env, validated to `dev` or `iis`.
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` from env.
- `INSTALLED_APPS`: `rest_framework`, `drf_spectacular`, `corsheaders`.
- `MIDDLEWARE`: `corsheaders.middleware.CorsMiddleware` (position 1).
- `CORS_ALLOWED_ORIGINS` from env (comma-split list), with `CORS_ALLOW_ALL_ORIGINS = True` only when `DEBUG=True`.
- `REST_FRAMEWORK` default renderer/parser classes, `DEFAULT_SCHEMA_CLASS` set to `drf_spectacular.openapi.AutoSchema`.
- `DEFAULT_AUTHENTICATION_CLASSES` set to empty list (auth handled by middleware, not DRF).
- `DEFAULT_PERMISSION_CLASSES` set to `AllowAny` (authorization handled by middleware).
- `SPECTACULAR_SETTINGS` with title, version, description.
- `CACHES` configured with `LocMemCache` default, `LDAP_CACHE_TTL` from env (default `300`).
- CSRF disabled for API (`CSRF_TRUSTED_ORIGINS` empty, views will use `@csrf_exempt`).

**Acceptance criteria:**
- `python manage.py check` exits 0.
- `python manage.py runserver` starts without errors and serves the DRF browsable API root (empty).

---

### Step 3: `api` app creation, empty packages, and init files

Create the `api` Django app with the package structure from the spec. All `__init__.py` files are created, all subpackages exist. No logic yet.

**Files created:**
- `backend/api/__init__.py`
- `backend/api/apps.py` — `ApiConfig` with `name = "api"`, `default_auto_field`.
- `backend/api/constants.py` — empty (placeholder).
- `backend/api/models.py` — empty (placeholder).
- `backend/api/urls.py` — empty `urlpatterns = []`.
- `backend/api/middleware/__init__.py`
- `backend/api/middleware/request_id.py` — empty (placeholder).
- `backend/api/middleware/authentication.py` — empty (placeholder).
- `backend/api/middleware/authorization.py` — empty (placeholder).
- `backend/api/views/__init__.py`
- `backend/api/views/health.py` — empty (placeholder).
- `backend/api/views/user.py` — empty (placeholder).
- `backend/api/serializers/__init__.py`
- `backend/api/services/__init__.py`
- `backend/api/adapters/__init__.py`

**`settings.py` updated:**
- Add `"api"` to `INSTALLED_APPS`.
- `config/urls.py` includes `api.urls` under `api/` prefix, plus `drf-spectacular` schema & docs URLs.

**Acceptance criteria:**
- `python manage.py check` exits 0.
- Directory structure matches spec tree exactly.

---

### Step 4: Test infrastructure and first green test

Set up the test harness so `pytest` discovers and runs tests. Write one trivial test to prove the pipeline works.

**Files created:**
- `backend/pytest.ini` — `DJANGO_SETTINGS_MODULE = config.settings`, `testpaths = tests`.
- `backend/mypy.ini` — configured for `django-stubs`, `djangorestframework-stubs`, strict mode.
- `backend/tests/__init__.py`
- `backend/tests/api/__init__.py`
- `backend/tests/api/views/__init__.py`
- `backend/tests/api/middleware/__init__.py`
- `backend/tests/conftest.py` — empty (placeholder for fixtures).
- `backend/tests/api/views/test_health.py` — single test: `TestHealthView::test_placeholder` that asserts `True`.

**Acceptance criteria:**
- `pytest` exits 0, shows 1 test passed.
- `pytest --cov=api --cov=config --cov-report=term-missing` runs without errors.
- `mypy api config` exits 0 with no errors.

---

## Phase 2 — Health endpoint (first real vertical slice)

### Step 5: Health view — tests first

Write the full test suite for the health endpoint before writing any implementation. Tests run and **all fail** (red).

**Files modified:**
- `backend/tests/api/views/test_health.py`

**Tests to write (`TestHealthView`):**
- `test_health_returns_200` — `GET /api/health/` returns HTTP 200.
- `test_health_returns_status_ok` — Response body is `{"status": "ok"}`.
- `test_health_allows_unauthenticated_access` — No `REMOTE_USER` header, still 200.
- `test_health_method_not_allowed_post` — `POST /api/health/` returns 405.
- `test_health_method_not_allowed_put` — `PUT /api/health/` returns 405.
- `test_health_method_not_allowed_delete` — `DELETE /api/health/` returns 405.

**Acceptance criteria:**
- `pytest` shows 6 tests, all **FAILED** or **ERROR** (red phase).

---

### Step 6: Health view — implementation (green)

Implement the minimum code to make all health tests pass.

**Files modified:**
- `backend/api/views/health.py` — `HealthView(APIView)` with `GET` returning `Response({"status": "ok"})`. `authentication_classes = []`, `permission_classes = [AllowAny]`.
- `backend/api/urls.py` — Route `health/` to `HealthView`.

**Acceptance criteria:**
- `pytest` shows 6 tests, all **PASSED** (green phase).
- `mypy api` exits 0.
- `python manage.py runserver` → `GET http://localhost:8000/api/health/` returns `{"status": "ok"}`.

---

## Phase 3 — Request-ID middleware

### Step 7: Request-ID middleware — tests first

**Files created:**
- `backend/tests/api/middleware/test_request_id.py`

**Tests to write (`TestRequestIdMiddleware`):**
- `test_response_contains_x_request_id_header` — Any response includes `X-Request-ID`.
- `test_request_id_is_valid_uuid4` — The header value is a valid UUID v4.
- `test_unique_request_ids_per_request` — Two sequential requests produce different IDs.
- `test_request_id_available_on_request_object` — The middleware attaches the ID to `request.META` or a custom attribute so downstream code can access it.

**Acceptance criteria:**
- New tests all **FAIL** (red).

---

### Step 8: Request-ID middleware — implementation (green)

**Files modified:**
- `backend/api/middleware/request_id.py` — `RequestIdMiddleware` class: generates UUID4, attaches to `request`, adds `X-Request-ID` response header.
- `backend/config/settings.py` — Add `api.middleware.request_id.RequestIdMiddleware` to `MIDDLEWARE`.

**Acceptance criteria:**
- All tests **PASS** (green).
- `mypy api` exits 0.
- Manual `curl` to `/api/health/` shows `X-Request-ID` header.

---

## Phase 4 — Authentication middleware (dev mode)

### Step 9: Dev mode auth guard — tests first

Implement the safety guard before any auth logic. The `AppConfig.ready()` check that prevents `AUTH_MODE=dev` when `DEBUG=False`.

**Files created:**
- `backend/tests/api/test_apps.py`

**Tests to write (`TestApiAppConfig`):**
- `test_dev_mode_allowed_when_debug_true` — No error raised.
- `test_dev_mode_raises_when_debug_false` — `ImproperlyConfigured` raised on `ready()`.
- `test_iis_mode_allowed_when_debug_false` — No error raised.
- `test_invalid_auth_mode_raises` — `ImproperlyConfigured` for unknown `AUTH_MODE` value.

**Acceptance criteria:**
- New tests all **FAIL** (red).

---

### Step 10: Dev mode auth guard — implementation (green)

**Files modified:**
- `backend/api/apps.py` — Add `ready()` method with the startup validation check.

**Acceptance criteria:**
- All tests **PASS** (green).
- `mypy api` exits 0.

---

### Step 11: Authentication middleware — tests first

**Files modified:**
- `backend/tests/api/middleware/test_authentication.py`

**Tests to write (`TestAuthenticationMiddleware`):**
- *Dev mode:*
    - `test_dev_mode_injects_mock_user` — Request gets `request.user` with username matching `DEV_USER_IDENTITY`.
    - `test_dev_mode_default_identity` — When `DEV_USER_IDENTITY` not set, defaults to `dev_admin`.
    - `test_dev_mode_creates_django_user` — A Django `User` object is created/retrieved for the mock identity.
- *IIS mode:*
    - `test_iis_mode_reads_remote_user` — `request.user.username` matches the `REMOTE_USER` header value.
    - `test_iis_mode_missing_remote_user_returns_401` — Request without `REMOTE_USER` is rejected with 401.
    - `test_iis_mode_creates_django_user_on_first_request` — A new `User` is created via `RemoteUserBackend`.
    - `test_iis_mode_reuses_existing_user` — Subsequent requests with same `REMOTE_USER` don't create duplicates.

**Acceptance criteria:**
- New tests all **FAIL** (red).

---

### Step 12: Authentication middleware — implementation (green)

**Files modified:**
- `backend/api/middleware/authentication.py` — `AuthenticationMiddleware` that branches on `AUTH_MODE`: dev mode injects a mock user, IIS mode delegates to Django's `RemoteUserMiddleware` / `RemoteUserBackend`.
- `backend/config/settings.py` — Add `api.middleware.authentication.AuthenticationMiddleware` to `MIDDLEWARE` (after request-ID), add `RemoteUserBackend` to `AUTHENTICATION_BACKENDS`.

**Acceptance criteria:**
- All tests **PASS** (green).
- `mypy api` exits 0.

---

## Phase 5 — Authorization middleware

### Step 13: Constants and role definitions

**Files modified:**
- `backend/api/constants.py` — Define `ROLE_ADMIN = "app_admin"`, `ROLE_VIEWER = "app_viewer"`, `ROLES = (ROLE_ADMIN, ROLE_VIEWER)`, and `AD_GROUP_TO_ROLE_MAP` dict mapping AD group names to app roles.

**Acceptance criteria:**
- `mypy api` exits 0.
- Constants importable: `from api.constants import ROLES`.

---

### Step 14: Authorization middleware — tests first

**Files created:**
- `backend/tests/api/middleware/test_authorization.py`

**Tests to write (`TestAuthorizationMiddleware`):**
- `test_user_with_admin_group_gets_admin_role` — LDAP returns admin group → `request.user.roles` contains `app_admin`.
- `test_user_with_viewer_group_gets_viewer_role` — LDAP returns viewer group → `request.user.roles` contains `app_viewer`.
- `test_user_with_multiple_groups_gets_multiple_roles` — User in both groups gets both roles.
- `test_user_with_no_matching_groups_returns_403` — LDAP returns groups not in map → 403 Forbidden.
- `test_unauthenticated_request_returns_401` — No user on request → 401.
- `test_ldap_result_is_cached` — Second request for same user does not trigger LDAP query (mock called once).
- `test_cache_respects_ttl` — After TTL expiry, LDAP is queried again.
- `test_health_endpoint_bypasses_authorization` — `GET /api/health/` is not subject to authorization checks.
- *Dev mode:*
    - `test_dev_mode_assigns_role_from_env` — `DEV_USER_ROLE=admin` → `request.user.roles` contains `app_admin`.
    - `test_dev_mode_defaults_to_admin` — When `DEV_USER_ROLE` not set, defaults to `app_admin`.

**Acceptance criteria:**
- New tests all **FAIL** (red).

---

### Step 15: Authorization middleware — implementation (green)

**Files modified:**
- `backend/api/middleware/authorization.py` — `AuthorizationMiddleware`: skips excluded paths (health), checks `request.user` exists, branches on `AUTH_MODE`. In `iis` mode: cache lookup → LDAP query via `ldap3` → map groups → cache store → attach roles or return 403. In `dev` mode: read `DEV_USER_ROLE` → map to role constant → attach.
- `backend/config/settings.py` — Add `api.middleware.authorization.AuthorizationMiddleware` to `MIDDLEWARE` (after authentication).

**Acceptance criteria:**
- All tests **PASS** (green).
- `mypy api` exits 0.

---

## Phase 6 — User endpoint

### Step 16: User serializer

**Files modified:**
- `backend/api/serializers/__init__.py` — `UserSerializer` with `username: str` and `roles: list[str]` fields.

**Acceptance criteria:**
- `mypy api` exits 0.

---

### Step 17: User view — tests first

**Files modified:**
- `backend/tests/api/views/test_user.py`

**Shared fixtures (in `tests/conftest.py`):**
- `admin_client` — Django test client with `REMOTE_USER` set, authorization middleware mocked to assign `app_admin`.
- `viewer_client` — Same, but with `app_viewer` role.
- `unauthenticated_client` — No `REMOTE_USER`.
- `unauthorized_client` — `REMOTE_USER` present but no matching AD groups (empty roles).

**Tests to write (`TestUserView`):**
- `test_admin_user_returns_200` — Admin client gets 200.
- `test_admin_user_response_contains_username` — Response `username` matches the `REMOTE_USER`.
- `test_admin_user_response_contains_admin_role` — Response `roles` includes `app_admin`.
- `test_viewer_user_returns_200` — Viewer client gets 200.
- `test_viewer_user_response_contains_viewer_role` — Response `roles` includes `app_viewer`.
- `test_unauthenticated_returns_401` — 401 when no user.
- `test_unauthorized_returns_403` — 403 when user has no roles.
- `test_method_not_allowed_post` — POST returns 405.
- `test_method_not_allowed_put` — PUT returns 405.
- `test_method_not_allowed_delete` — DELETE returns 405.

**Acceptance criteria:**
- New tests all **FAIL** (red).

---

### Step 18: User view — implementation (green)

**Files modified:**
- `backend/api/views/user.py` — `UserView(APIView)` with `GET` that reads `request.user.username` and `request.user.roles`, returns via `UserSerializer`.
- `backend/api/urls.py` — Route `user/` to `UserView`.

**Acceptance criteria:**
- All tests **PASS** (green).
- `mypy api` exits 0.
- Manual test: `python manage.py runserver` → `GET /api/user/` returns `{"username": "dev_admin", "roles": ["app_admin"]}` (dev mode).

---

## Phase 7 — API documentation endpoints

### Step 19: Spectacular URLs — tests first

**Files created:**
- `backend/tests/api/views/test_schema.py`

**Tests to write (`TestSchemaEndpoints`):**
- `test_schema_returns_200` — `GET /api/schema/` returns 200.
- `test_schema_returns_json` — Content-Type is `application/vnd.oai.openapi+json` or `application/json`.
- `test_docs_returns_200` — `GET /api/docs/` returns 200.
- `test_docs_returns_html` — Content-Type is `text/html`.

**Acceptance criteria:**
- Tests **FAIL** (red).

---

### Step 20: Spectacular URLs — implementation (green)

**Files modified:**
- `backend/config/urls.py` — Add `SpectacularAPIView`, `SpectacularSwaggerView` at `/api/schema/` and `/api/docs/`.

**Acceptance criteria:**
- All tests **PASS** (green).
- `GET /api/docs/` renders Swagger UI in browser.

---

## Phase 8 — Coverage, types, and polish

### Step 21: Full coverage audit

Run `pytest --cov=api --cov=config --cov-report=term-missing` and identify any uncovered lines.

**Write additional tests to fill gaps:**
- `backend/tests/config/test_settings.py` — Test that settings load correctly for both `AUTH_MODE=dev` and `AUTH_MODE=iis` configurations.
- `backend/tests/config/test_wsgi.py` — Test WSGI application is importable and callable.

**Acceptance criteria:**
- `pytest --cov=api --cov=config` reports **100%** line coverage.

---

### Step 22: MyPy strict pass

Run `mypy api config` and fix any remaining type errors. Add type annotations to all function signatures, middleware classes, and view methods.

**Acceptance criteria:**
- `mypy api config` exits 0 with 0 errors in strict mode.

---

### Step 23: `.env.example` and final file audit

Create the example env file and verify every file in the spec's directory tree exists.

**Files created/verified:**
- `backend/.env.example` — All env vars from the Configuration Reference table, commented with descriptions.

**Acceptance criteria:**
- `find` output matches the spec's directory tree exactly (no extra, no missing files).
- `python manage.py check --deploy` exits 0 (with `.env` configured for production-like values).

---

## Phase 9 — Deployment

### Step 24: Follow deployment steps in spec.md

Execute the deployment procedure defined in the [Deployment section of spec.md](/docs/spec.md#deployment), steps 1–11. This is performed on the target Windows Server 2022 instance.

**Acceptance criteria:**
- All 11 deployment steps completed.
- All sanity checks pass.
- End-to-end verification table (step 11) passes all 6 checks.