# Implementation Plan — Rate Limiting & Cache Control

*Adds per-user, per-endpoint rate limiting using a `@throttle` decorator and explicit HTTP cache-control using `@cache_public`, `@cache_private`, and `@cache_disabled` decorators. Both decorator families are enforced at the middleware layer — every view must declare all three policy families (auth, throttle, cache) or the application raises `ImproperlyConfigured`. See [spec.md — Rate Limiting](/docs/spec.md#rate-limiting) and [spec.md — Caching](/docs/spec.md#caching) for design rationale and [CONTRIBUTING.md](/docs/CONTRIBUTING.md) for the delivery workflow.*

**Baseline:** 96 tests, 100% coverage, mypy clean, ruff clean.
**Final:** 147 tests, 100% coverage, mypy clean, ruff clean. All steps complete.

---

## Phase 1 — Throttle Infrastructure

### Step 01: Add `api/throttling.py` — throttle decorator and custom throttle class

**What:** Create `api/throttling.py` containing `RemoteUserRateThrottle` (a `SimpleRateThrottle` subclass keyed on `REMOTE_USER` identity) and a `@throttle(rate)` decorator that applies per-view rate limiting to DRF `APIView` classes, Django `View` classes, and function-based views. The rate is specified directly in the decorator — no centralised settings or environment variables.

**Files created:**
- `backend/api/throttling.py`

**Details:**
- `RemoteUserRateThrottle` extends `rest_framework.throttling.SimpleRateThrottle`.
- Overrides `__init__` to skip default rate parsing (rate is resolved per-request).
- Overrides `allow_request(self, request, view)`:
  - Reads rate from `view._throttle_rate` (set by the decorator).
  - Returns `True` if no rate is set (no throttling).
  - Sets `self.scope` to `type(view).__name__` for cache-key isolation.
  - Delegates to `super().allow_request()` for the actual fixed-window check.
- Overrides `get_cache_key(self, request, view)`:
  - If `request.user` exists and `is_authenticated`, use `user.get_username()` as the identity.
  - Otherwise, fall back to `self.get_ident(request)` (IP-based).
- `throttle(rate: str)` decorator:
  - For DRF `APIView` subclasses: sets `_throttle_rate` and `throttle_classes = [RemoteUserRateThrottle]`.
  - For Django `View` subclasses: sets `_throttle_rate` and wraps `dispatch` with a manual throttle check returning `429 JsonResponse` on denial.
  - For callables (function-based views): wraps the function with a throttle check returning `429 JsonResponse` on denial.

**Acceptance criteria:**
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.
- `uv run pytest -q` — all 96 existing tests still pass (no new tests yet).
- `uv run python manage.py check` — 0 issues.

---

### Step 02: Add tests for `api/throttling.py`

**What:** Create `backend/tests/api/test_throttling.py` with comprehensive tests for the throttle class and the `@throttle` decorator.

**Files created:**
- `backend/tests/api/test_throttling.py`

**Details:**

Tests for `RemoteUserRateThrottle`:
- `TestRemoteUserRateThrottle`:
  - `test_authenticated_user_cache_key_contains_username` — Verify the cache key includes the username when authenticated.
  - `test_unauthenticated_request_cache_key_falls_back_to_ip` — Verify IP-based identity when no user present.
  - `test_cache_key_scope_uses_view_class_name` — Verify scope in cache key uses the view class name.
  - `test_allow_request_returns_true_when_no_rate` — Verify requests pass when no `_throttle_rate` is set.

Tests for `@throttle` on Django `View` classes:
- `TestThrottleDecoratorOnDjangoView`:
  - `test_allows_request_under_limit` — Verify requests under the limit pass through.
  - `test_blocks_request_over_limit` — Verify `1/minute` rate blocks the second request with 429 + error envelope.
  - `test_includes_retry_after_header` — Verify 429 includes `Retry-After` header.
  - `test_preserves_view_class_attributes` — Verify decorator preserves `authz_policy` and other metadata.
  - `test_sets_throttle_rate_attribute` — Verify rate is stored on the class for introspection.

Tests for `@throttle` on function-based views:
- `TestThrottleDecoratorOnFunction`:
  - `test_allows_request_under_limit` — Verify requests under the limit pass through.
  - `test_blocks_request_over_limit` — Verify `1/minute` rate blocks the second request with 429.
  - `test_includes_retry_after_header` — Verify 429 includes `Retry-After` header.
  - `test_sets_throttle_rate_attribute` — Verify rate is stored on the function.

Helper tests:
- `TestThrottleHelpers`:
  - `test_throttle_wait_seconds_handles_none` — Verify `None` wait returns `None`.
  - `test_throttle_detail_without_wait_uses_default_message` — Verify DRF default message.

**Acceptance criteria:**
- `uv run pytest -q` — all tests pass.
- `uv run pytest` — 100% coverage.
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.

---

## Phase 2 — View Integration

### Step 03: Apply `@throttle` to DRF views (`HealthView`, `SchemaView`, `SwaggerDocsView`)

**What:** Add the `@throttle` decorator with explicit rate strings to all DRF `APIView` subclasses.

**Files modified:**
- `backend/api/views/health.py` — Add `@throttle("60/minute")` to `HealthView`.
- `backend/api/views/docs.py` — Add `@throttle("30/minute")` to `SwaggerDocsView` and `@throttle("10/minute")` to `SchemaView`.

**Details:**
- The `@throttle` decorator sets `throttle_classes` and `_throttle_rate` on the class. DRF's built-in throttle machinery reads the rate from the view instance.
- Decorator ordering: `@throttle` outermost, then `@authz_*`.
- Import `throttle` from `api.throttling`.

**Acceptance criteria:**
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.
- `uv run pytest -q` — all existing tests still pass.
- `uv run python manage.py check` — 0 issues.

---

### Step 04: Apply `@throttle` to Django `View` (`UserView`)

**What:** Add `@throttle("30/minute")` to `UserView`, which is a plain Django `View`.

**Files modified:**
- `backend/api/views/user.py` — Add `@throttle("30/minute")` to `UserView`.

**Details:**
- The decorator wraps `dispatch()` to check the throttle before the view processes the request.
- On throttle denial, returns a `429 JsonResponse` with the standard error envelope.
- Decorator ordering: `@throttle` outermost, then `@authz_roles`.
- Import `throttle` from `api.throttling`.

**Acceptance criteria:**
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.
- `uv run pytest -q` — all existing tests still pass.
- `uv run python manage.py check` — 0 issues.

---

### Step 05: Add throttle integration tests for all endpoints

**What:** Add integration tests that verify rate limiting works end-to-end on every endpoint.

**Files modified:**
- `backend/tests/api/views/test_health.py` — Add throttle tests to `TestHealthView`.
- `backend/tests/api/views/test_user.py` — Add throttle tests to `TestUserView`.

**Files created:**
- `backend/tests/api/views/test_docs.py` — Add throttle tests for docs/schema views (if not already present; otherwise modify existing file).

**Details:**

Each throttle integration test:
1. Patches `_throttle_rate` on the view class to an aggressive rate (e.g., `"1/minute"`).
2. Sends two rapid requests.
3. Asserts the second returns 429 with `"throttled"` in `detail`, `request_id` present, and `Retry-After` header.
4. Restores the original rate after the test.

All tests clear the cache for isolation.

**Acceptance criteria:**
- `uv run pytest -q` — all tests pass.
- `uv run pytest` — 100% coverage.
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.

---

## Phase 3 — Final Validation

### Step 06: Full quality gate and final validation

**What:** Run the complete quality gate suite to confirm everything is wired correctly and no regressions exist.

**Commands (all must pass):**

```bash
uv run pytest -q
uv run pytest                     # with coverage — must show 100%
uv run mypy api config            # 0 errors
uv run ruff check .               # all checks passed
uv run python manage.py check     # 0 issues
```

**Validation checklist:**
- [ ] All tests pass (expected: baseline + new throttle tests).
- [ ] 100% coverage — no regressions.
- [ ] `mypy` clean — all new code fully typed.
- [ ] `ruff` clean — no linting issues.
- [ ] Django system check clean.
- [ ] All new modules, classes, and functions have docstrings.
- [ ] Each endpoint has an explicit `@throttle` decorator with a rate string.
- [ ] 429 responses include standard error envelope (`detail` + `request_id`) and `Retry-After` header.

---

## Phase 4 — Cache Control & Decorator Enforcement

### Step 07: Add `api/caching.py` — cache-control decorators

**What:** Create `api/caching.py` containing three HTTP cache-control decorators: `@cache_public(max_age=N)`, `@cache_private`, and `@cache_disabled`. Every view must declare one, even if caching is explicitly disabled. The decorators set both a metadata attribute (`_cache_policy`) for middleware enforcement and wrap `dispatch` to apply `Cache-Control` headers via `django.utils.cache.patch_cache_control`.

**Files created:**
- `backend/api/caching.py`

**Details:**
- `CACHE_POLICY_ATTR = "_cache_policy"` — constant for the metadata attribute name.
- `cache_public(*, max_age: int)` — parametric decorator. Sets `_cache_policy = "public"` and wraps dispatch with `public=True, max_age=N`.
- `cache_private(target)` — direct decorator. Sets `_cache_policy = "private"` and wraps dispatch with `private=True, no_cache=True`.
- `cache_disabled(target)` — direct decorator. Sets `_cache_policy = "disabled"` and wraps dispatch with `no_store=True`.
- Internal helpers `_apply_cache_headers_class(cls, **kwargs)` and `_apply_cache_headers_callable(func, **kwargs)` handle DRF `APIView`, Django `View`, and plain callable targets.
- All three raise `TypeError` for invalid targets (e.g., strings).

**Acceptance criteria:**
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.
- `uv run pytest -q` — all 122 existing tests still pass.
- `uv run python manage.py check` — 0 issues.

---

### Step 08: Add `@throttle_exempt` to `api/throttling.py`

**What:** Add a `throttle_exempt` decorator that marks a view as explicitly not rate-limited, satisfying the middleware enforcement check without applying any throttle.

**Files modified:**
- `backend/api/throttling.py`

**Details:**
- `throttle_exempt(target)` — sets `_throttle_rate = None` on the target. No dispatch wrapping needed because `allow_request` already returns `True` for `None` rate.
- Export `THROTTLE_RATE_ATTR = "_throttle_rate"` constant for use by the enforcement middleware.

**Acceptance criteria:**
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.
- `uv run pytest -q` — all existing tests still pass.

---

### Step 09: Extract decorator enforcement into dedicated middleware

**What:** Create a separate `DecoratorEnforcementMiddleware` in `api/middleware/enforcement.py` that checks every project view has explicit `_throttle_rate`, `_cache_policy`, and `authz_policy` attributes. This separates the "are all decorators present?" concern from the authorization middleware's "enforce the auth policy" concern.

**Files created:**
- `backend/api/middleware/enforcement.py`

**Files modified:**
- `backend/api/middleware/authorization.py` — Remove `_is_project_view`, `_has_view_attr` helpers, throttle/cache enforcement checks, and `CACHE_POLICY_ATTR`/`THROTTLE_RATE_ATTR` imports. Authorization middleware now only handles auth policy enforcement.
- `backend/config/settings.py` — Register `DecoratorEnforcementMiddleware` in `MIDDLEWARE` list between `AuthenticationMiddleware` and `AuthorizationMiddleware`.

**Details:**
- `DecoratorEnforcementMiddleware` uses `process_view` to check all three decorator families.
- Runs before `AuthorizationMiddleware` so misconfigured views are caught before any LDAP or auth work.
- Contains `_is_project_view` and `_has_view_attr` helpers (previously on `AuthorizationMiddleware`).
- Non-project views raise `ImproperlyConfigured` (strict mode preserved).
- `AuthorizationMiddleware` retains `_get_view_attr` for reading auth policy/roles values.

**Acceptance criteria:**
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.
- `uv run pytest -q` — all existing tests still pass (dummy views in auth tests updated with both attributes).
- `uv run python manage.py check` — 0 issues.

---

### Step 10: Apply cache decorators to all views

**What:** Add the appropriate `@cache_*` decorator to every view, following the decorator ordering convention: `@throttle` outermost → `@cache_*` middle → `@authz_*` innermost.

**Files modified:**
- `backend/api/views/health.py` — Replace `@method_decorator(cache_control(...))` on `get` with `@cache_public(max_age=5)` at class level.
- `backend/api/views/docs.py` — Add `@cache_private` to `SchemaView` and `SwaggerDocsView`.
- `backend/api/views/user.py` — Add `@cache_private` at class level; remove manual `response["Cache-Control"]` assignment from `get`.

**Acceptance criteria:**
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.
- `uv run pytest -q` — all existing tests still pass.
- `uv run python manage.py check` — 0 issues.

---

### Step 11: Add tests for caching, throttle_exempt, and enforcement

**What:** Add comprehensive tests for the new caching module, throttle_exempt decorator, and middleware enforcement checks.

**Files created:**
- `backend/tests/api/test_caching.py` — 15 tests across 4 classes covering all cache decorators.

**Files created:**
- `backend/tests/api/test_caching.py` — 15 tests across 4 classes covering all cache decorators.
- `backend/tests/api/middleware/test_enforcement.py` — 9 tests for the decorator enforcement middleware.

**Files modified:**
- `backend/tests/api/test_throttling.py` — Add `TestThrottleExempt` class (3 tests).
- `backend/tests/api/middleware/test_authorization.py` — Remove `TestDecoratorEnforcement` class (moved to `test_enforcement.py`); remove `_throttle_rate`/`_cache_policy` from dummy views (no longer checked by this middleware); remove `test_non_project_view_raises_improperly_configured` and `test_is_project_view_returns_false_for_none` (moved to enforcement tests).

**Details:**

`test_caching.py`:
- `TestCachePublicDecorator` (6 tests): policy attr on DRF view, Django view, callable; `Cache-Control: public, max-age=5` header; TypeError for invalid target; preserves existing attributes.
- `TestCachePrivateDecorator` (4 tests): policy attr on DRF view; `Cache-Control: private, no-cache` header; TypeError for invalid target; works on callable.
- `TestCacheDisabledDecorator` (4 tests): policy attr on DRF view; `Cache-Control: no-store` header; TypeError for invalid target; works on callable.
- `TestCacheCallableNonResponse` (1 test): non-response passthrough from wrapped callable.

`test_enforcement.py`:
- `test_fully_decorated_view_passes` — All three decorators present passes enforcement.
- `test_missing_throttle_raises_improperly_configured` — View without `_throttle_rate` raises error.
- `test_missing_cache_raises_improperly_configured` — View without `_cache_policy` raises error.
- `test_missing_auth_raises_improperly_configured` — View without `authz_policy` raises error.
- `test_throttle_exempt_satisfies_enforcement` — `_throttle_rate = None` passes check.
- `test_non_project_view_raises_improperly_configured` — Non-project views rejected.
- `test_is_project_view_returns_false_for_none` — `None` handled safely.
- `test_has_view_attr_reads_from_function` — Direct function attribute lookup.
- `test_has_view_attr_reads_from_view_class` — `view_class` attribute lookup through `as_view()`.

`test_throttling.py` additions:
- `test_sets_throttle_rate_none_on_class` — Verify `_throttle_rate = None` on a class.
- `test_sets_throttle_rate_none_on_callable` — Verify `_throttle_rate = None` on a function.
- `test_exempt_view_allows_unlimited_requests` — Verify exempt view never returns 429.

**Acceptance criteria:**
- `uv run pytest -q` — 147 tests pass.
- `uv run pytest` — 100% coverage.
- `uv run mypy api config` — 0 errors.
- `uv run ruff check .` — all checks passed.

---

### Step 12: Final quality gate and documentation

**What:** Run the complete quality gate suite, update `docs/spec.md` with caching and enforcement documentation.

**Commands (all must pass):**

```bash
uv run pytest -q
uv run pytest                     # with coverage — must show 100%
uv run mypy api config            # 0 errors
uv run ruff check .               # all checks passed
uv run python manage.py check     # 0 issues
```

**Validation checklist:**
- [ ] All 147 tests pass.
- [ ] 100% coverage — no regressions.
- [ ] `mypy` clean — all new code fully typed.
- [ ] `ruff` clean — no linting issues.
- [ ] Django system check clean.
- [ ] Every view has explicit `@throttle`/`@throttle_exempt`, `@cache_*`, and `@authz_*` decorators.
- [ ] `DecoratorEnforcementMiddleware` raises `ImproperlyConfigured` for any missing decorator family.
- [ ] `AuthorizationMiddleware` handles only auth policy enforcement (no throttle/cache checks).
- [ ] `docs/spec.md` updated with enforcement middleware documentation.
- [ ] No throttle-related environment variables or centralised `DEFAULT_THROTTLE_RATES` in settings.