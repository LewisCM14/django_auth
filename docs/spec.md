# Django Authentication & Authorization

*A minimal Django web application designed for use within corporate enterprise to be deployed specifically to Windows servers that uses IIS for Authentication and Activate Directory for Authorization. Able to scale and extend for a multitude of use cases by utilizing the Adapter pattern.*

## Table of Contents
- [Requirement](#requirement)
- [Design](#design)
    - [Application Architecture Diagram](#application-architecture-diagram)
    - [Workflow](#workflow)
    - [Structure](#structure)
    - [Endpoints](#endpoints)
    - [Logging](#logging)
    - [Exception Handling](#exception-handling)
    - [Caching](#caching)
    - [Automated Testing Strategy](#automated-testing-strategy)
    - [Local Development](#local-development)
- [Deployment](#deployment)

## Requirement

- Must run on Windows Server 2022.
- Must use `Python==3.14` & `Django>=6.0.0`.
- Must integrate with the `djangorestframework>=3.0.0`.
- Must integrate with `drf-spectacular` for provision of API documentation.
- The application must use Windows Authentication via IIS, integrating directly with Active Directory for user authentication. 
- All authentication must be handled by IIS; the application will not implement its own login or token validation. User identity is provided to the backend via IIS environment variables or headers.
- For authorization, the application must query Active Directory via LDAP to determine user group membership and map to application roles.
    - Specifically `ldap3>=2.9`.
    - LDAP group membership is queried on every request that requires role-based authorization. Results are **not cached** — AD group changes (additions, removals, disablements) must take immediate effect for security. The additional LDAP latency per request is acceptable for this use case.
    - Users not in a configured group are to be denied access to the application.
- Must integrate with `python-dotenv` for loading environment variables from `.env` files.
- Must integrate with `django-cors-headers` for Cross-Origin Resource Sharing (CORS) support, enabling both same-origin and cross-origin frontend deployments.
- All packages must be available through **Anaconda**, prioritizing the `conda-forge` channel, for production deployment on Windows.
    - Local development uses `uv` with `pyproject.toml` as the primary dependency manifest. `environment.yml` is maintained in parallel for Anaconda.
    - `django-auth-ldap`, `python-ldap` & `django-auth-adfs` cannot be used as these are not readily available for `Windows` on `conda-forge`.
- All technologies used must be license free for corporate use.
- The application must support local development and testing without IIS/AD/LDAP.
- All code must have 100% test coverage using the `pytest` testing harness and Django specific testing libraries are required.
- All code must be statically typed using the `MyPy` library.
- The application is to be scope to include the below roles in its current state, with a clear method for adding further roles:
    - `app_admin`
    - `app_viewer`

## Design

*Design intention is to use the `Representational State Transfer (REST)` protocol to provide `Backend-for-Frontend (BFF)` endpoints as the primary API style for the application. All authentication and authorization needs are handled by IIS using Windows Authentication and Active Directory. The backend receives user identity via IIS-provided `REMOTE_USER`. The application is served via WSGI (using `wfastcgi` under IIS in production). HTTPS is enforced at the IIS layer; the Django application assumes all traffic is TLS-terminated by the reverse proxy. CSRF protection is disabled for API views, as authentication is handled entirely by IIS via the `REMOTE_USER` header and no session or cookie-based authentication is used. CORS is managed via `django-cors-headers`, supporting both same-origin deployments (where the frontend is served by the same IIS instance) and cross-origin deployments (where the frontend is hosted separately).*

### Application Architecture Diagram

```mermaid
---
title: Application Architecture — Level 0
---
flowchart LR
    User(["Corporate User"])
    FE["Frontend Application"]
    System["Django Auth &amp; Authorization"]
    AD[("Active Directory")]

    User -- "Windows credentials" --> FE
    FE -- "HTTPS" --> System
    System -- "LDAP group membership query" --> AD
```

```mermaid
---
title: Application Architecture — Level 1
---
flowchart LR
    User(["Corporate User"])
    FE["Frontend Application\n(Browser)"]
    AD[("Active Directory\n(LDAP)")]

    subgraph IIS_Host["IIS — Windows Server 2022"]
        WinAuth["Windows\nAuthentication"]
        Proxy["Reverse Proxy\nHTTPS Termination"]
    end

    subgraph Django["Django Application — WSGI"]
        MW_RID["Request-ID\nMiddleware"]
        MW_AuthN["Authentication\nMiddleware\n(RemoteUserMiddleware)"]
        MW_AuthZ["Authorization\nMiddleware"]
        API["API Layer\n(DRF Views &amp; Serializers)"]
        SVC["Service Layer"]
        ADP["Source Adapter Layer"]
        DB[("Persistence Layer\n(Django ORM)")]
    end

    User -- "Windows credentials" --> FE
    FE -- "HTTPS" --> WinAuth
    WinAuth -- "REMOTE_USER" --> Proxy
    Proxy -- "WSGI (wfastcgi)" --> MW_RID
    MW_RID --> MW_AuthN
    MW_AuthN --> MW_AuthZ
    MW_AuthZ -- "LDAP lookup\n(per-request, @authz_roles only)" --> AD
    MW_AuthZ --> API
    API --> SVC
    SVC --> ADP
    SVC --> DB
    ADP -- "External sources" --> ADP
```

### Workflow

1. API Layer (`Django REST Framework (DRF)`)
    - Exposes stable endpoints.
    - Leverages Django's built-in `RemoteUserMiddleware` and `RemoteUserBackend` to authenticate the IIS-provided `REMOTE_USER`.
    - Uses `ldap3` library to query Active Directory for group membership on every `@authz_roles` request. Results are not cached — AD changes take immediate effect.
    - Maps AD group membership to Django user roles for authorization (e.g., admin access).
    - Enforces explicit per-view authorization policy declaration using permission decorators in `api/permissions.py`:
        - `@authz_public` — no authentication or authorization required (e.g. health probes)
        - `@authz_authenticated` — IIS authentication required, no specific role (e.g. API docs)
        - `@authz_roles(...)` — IIS authentication required with one or more specific roles
    - Every view must declare exactly one of these decorators. Views that omit a decorator raise `ImproperlyConfigured` at request time. There are no default permissions — future developers must explicitly set authorization at the view level.
    - LDAP group membership is only queried for views decorated with `@authz_roles(...)`. Views using `@authz_public` or `@authz_authenticated` never trigger an LDAP lookup.
    - Strict mode: routed endpoints must be implemented in `api.views`. Third-party endpoints (for example drf-spectacular schema/docs) must be exposed through wrapper views in `api.views` and decorated explicitly.
    - All unhandled exceptions in DRF views are caught by the custom exception handler (`api/exceptions.py`), which logs the error and returns a standardised error envelope with `request_id` correlation. No per-view `try/except` blocks are needed.
    - Per-request access logging (method, path, status, duration, user) is handled by `RequestIdMiddleware`. Views do not implement their own request/response logging.

1. Service Layer
    - Implements business workflows.
    - Orchestrates internal DB operations and/or external source reads.
    - Transforms and normalizes external/internal payloads into canonical response objects for the UI.
    - Uses standard Python logging (`logging.getLogger(__name__)`); request-ID correlation is automatic via the context variable and logging filter.
    - Raises DRF `APIException` subclasses for expected error conditions (e.g., business rule violations). Unexpected exceptions propagate to the exception handler, which logs and returns a safe 500.
    - Can cache computed results via Django's cache framework using the `service:{domain}:{operation}:{hash}` key convention.

1. Source Adapter Layer
    - One adapter per external source.
    - Handles source-specific authentication, request/response contracts, retries, and error mapping.
    - Performs minimal parsing: converts raw responses to native Python structures, handles protocol-level details, and validates required fields, but does not apply business rules or normalization (handled in the application & mapping layer).
    - Logs external call lifecycle (start, response status, retries, failures) at appropriate levels (`INFO` / `WARNING` / `ERROR`). Request-ID correlation is automatic.
    - Caches external responses via Django's cache framework with source-appropriate TTLs, using the `adapter:{source}:{resource}:{id}` key convention.
    - Raises standard Python exceptions on failure. The exception handler catches these, logs the traceback, and returns a safe 500 response.

1. Persistence Layer (`Django ORM`)
    - Uses Django models and migrations for internal schema evolution.
    - Keeps write operations limited to app-owned internal tables.
    - Service-layer writes explicitly invalidate related cache keys after successful database commits (write-through invalidation pattern).

```mermaid
---
title: Application Workflow - Level 0
---
flowchart TD
    subgraph API_Layer["API Layer (DRF)"]
        V[Views]
        S[Serializers]
    end
    subgraph Service_Layer[Service Layer]
        BL[Business Logic & Orchestration]
        NORM[Normalization & Mapping]
    end
    subgraph Adapter_Layer[Source Adapter Layer]
        AD["Adapters"]
    end
    subgraph Persistence_Layer[Persistence Layer]
        DB[(Django ORM)]
    end
    subgraph Cross_Cutting["Cross-cutting Concerns (spans all layers)"]
        LOG["Logging — request-ID correlated via contextvars"]
        EXC["Exception Handler — standardised error envelope"]
        CACHE[("Cache — LocMemCache / Redis")]
    end

    V -->|Raw request data| S
    S -->|Validated data| BL
    BL -->|Invoke| NORM
    NORM -->|Fetch/Join| AD
    AD -->|Raw/parsed data| NORM
    BL -->|DB ops| DB
    NORM -->|Canonical response| S
    S -->|Serialize output| V

    EXC -.->|Catches unhandled exceptions| V
    CACHE -.->|Adapter data| AD
    CACHE -.->|Computed results| BL
```

```mermaid
---
title: Authentication, Authorization & Cross-cutting Concerns — Level 1
---
sequenceDiagram
    actor User as Corporate User
    participant FE as Frontend
    participant IIS as IIS (Windows Auth + HTTPS)
    participant RID as Request-ID Middleware
    participant AuthN as Authentication Middleware<br/>(RemoteUserMiddleware)
    participant AuthZ as Authorization Middleware
    participant Cache as Django Cache
    participant AD as Active Directory (LDAP)
    participant View as DRF View
    participant EH as Exception Handler<br/>(api/exceptions.py)

    User->>FE: Interact with application
    FE->>IIS: HTTPS request (Kerberos/NTLM)
    IIS->>IIS: Windows Authentication
    alt Authentication fails at IIS
        IIS-->>FE: 401 Unauthorized
    else Authentication succeeds
        IIS->>RID: WSGI request + REMOTE_USER header
        RID->>RID: Generate & attach X-Request-ID
        Note over RID: Store request-ID in contextvars<br/>Log INFO: request received<br/>(method, path, user)
        RID->>AuthN: Forward request

        alt AUTH_MODE = dev
            AuthN->>AuthN: Inject mock identity<br/>(DEV_USER_IDENTITY)
        else AUTH_MODE = iis
            AuthN->>AuthN: Read REMOTE_USER,<br/>create/update Django User<br/>via RemoteUserBackend
        end

        AuthN->>AuthZ: Forward authenticated request

        AuthZ->>AuthZ: Read view decorator policy

        alt @authz_public (e.g. /api/health/)
            AuthZ->>View: Forward request (no auth checks)
        else @authz_authenticated (e.g. /api/docs/)
            AuthZ->>AuthZ: Verify REMOTE_USER present
            alt Not authenticated
                Note over AuthZ: Log WARNING: 401 denied<br/>(username, path, policy)
                AuthZ-->>FE: 401 JSON envelope + request_id
            else Authenticated
                AuthZ->>View: Forward request (no role check)
            end
        else @authz_roles(...) (e.g. /api/user/)
            AuthZ->>AuthZ: Verify REMOTE_USER present
            alt Not authenticated
                Note over AuthZ: Log WARNING: 401 denied<br/>(username, path, policy)
                AuthZ-->>FE: 401 JSON envelope + request_id
            else Authenticated
                AuthZ->>AD: LDAP query (user group membership)
                AD-->>AuthZ: Group list
                AuthZ->>AuthZ: Map AD groups → app roles

                alt No matching roles
                    Note over AuthZ: Log WARNING: 403 denied<br/>(username, path, required roles)
                    AuthZ-->>FE: 403 JSON envelope + request_id
                else Roles match
                    AuthZ->>AuthZ: Attach roles to request.user
                    AuthZ->>View: Forward authorized request
                end
            end
        end

        alt View raises unhandled exception
            View->>EH: Exception propagates to DRF handler
            Note over EH: Log ERROR: full traceback<br/>with request-ID correlation
            EH-->>FE: 500 JSON envelope + request_id<br/>("An unexpected error occurred.")
        else Normal processing
            View->>View: Process & build response
            View-->>FE: 200 OK (response payload)
        end

        Note over RID: Log INFO: response completed<br/>(status, duration ms, request-ID)
    end
    FE-->>User: Render UI
```

### Structure

The `api` Django app is organized into domain-aligned packages that mirror the layered architecture detailed above.

```
backend/
├── api/
│   ├── __init__.py
│   ├── apps.py
│   ├── constants.py
│   ├── exceptions.py
│   ├── models.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── request_id.py
│   │   ├── authentication.py
│   │   └── authorization.py
│   ├── permissions.py
│   ├── urls.py
│   ├── views/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   └── user.py
│   ├── serializers/
│   │   ├── __init__.py
│   │   └── user_serializer.py
│   ├── services/
│   │   └── __init__.py
│   ├── adapters/
│   │   └── __init__.py
│   └── migrations/
├── config/
│     ├── __init__.py
│     ├── settings.py
│     ├── urls.py
│     └── wsgi.py
├── tests/
├── .env.example
├── manage.py
├── mypy.ini
├── pytest.ini
├── pyproject.toml
└── environment.yml
```

**Package responsibilities:**

| File/Package                        | Layer                | Responsibility |
|-------------------------------------|----------------------|----------------|
| `api/`                              | All backend layers   | Main Django app (see below for subfolders) |
| `api/apps.py`                       | API                  | Django app config with startup security guard (validates AUTH_MODE and DEBUG settings) |
| `api/constants.py`                  | Cross-cutting        | Role definitions (ROLE_ADMIN, ROLE_VIEWER), AD group-to-role mapping |
| `api/exceptions.py`                 | Cross-cutting        | Custom DRF exception handler — standardises all error responses and logs exceptions with request-ID correlation |
| `api/models.py`                     | Persistence          | ORM models |
| `api/middleware/`                   | API/Cross-cutting    | Middleware package (see below) |
| `api/middleware/request_id.py`      | Cross-cutting        | Request-ID injection middleware |
| `api/middleware/authentication.py`  | API                  | `RemoteUserMiddleware` integration and dev-mode identity injection |
| `api/middleware/authorization.py`   | API                  | LDAP group membership lookup, role mapping, and access control |
| `api/urls.py`                       | API                  | URL routing to views package |
| `api/views/`                        | API                  | HTTP request handling, input validation, response shaping |
| `api/views/health.py`               | API                  | Health check endpoint |
| `api/views/docs.py`                 | API                  | Wrapper views for schema/docs endpoints with explicit auth policy |
| `api/views/user.py`                 | API                  | User identity and role endpoint |
| `api/permissions.py`                | API/Cross-cutting    | Per-view authorization permission decorators (`@authz_public`, `@authz_authenticated`, `@authz_roles`) |
| `api/serializers/`                  | API                  | Serializer package and export surface |
| `api/serializers/user_serializer.py`| API                  | User identity/roles response serializer (`UserSerializer`) |
| `api/services/`                     | Service              | Business logic, orchestration, state machines, normalization & mapping |
| `api/adapters/`                     | Source Adapter       | External data-source access with resilience patterns |
| `api/migrations/`                   | Persistence          | Django migration history |
| `config/`                           | Cross-cutting        | Django and app configuration (settings, WSGI, logging, etc.) |
| `config/logging.py`                 | Cross-cutting        | `JsonFormatter` — custom `logging.Formatter` subclass for structured JSON output |
| `tests/`                            | Cross-cutting        | All automated tests (unit, integration, contract); mirrors backend structure |

### Endpoints

**Get Health** (`GET /api/health/`)

Returns the application status. This endpoint is unauthenticated and publicly accessible — no `REMOTE_USER` or role membership is required. Intended for use by load balancers, uptime monitors, and IIS health probes.

Implementation note: this endpoint is explicitly marked with `@authz_public` at the view level.

| Property        | Value                      |
|-----------------|----------------------------|
| Method          | `GET`                      |
| URL             | `/api/health/`             |
| Authentication  | None                       |
| Authorization   | None                       |
| View            | `api/views/health.py`      |

*Response* `200 OK`
```json
{
    "status": "ok"
}
```

---

**Get User** (`GET /api/user/`)

Returns the authenticated user's identity and assigned roles. Requires a valid `REMOTE_USER` (provided by IIS in production or injected by dev-mode middleware locally). The authorization middleware resolves the user's AD group memberships (via LDAP, queried per-request) and maps them to application roles before the request reaches this view.

Designed to be called by the frontend on initial load to populate a context provider (`UserContext`) or state store (e.g., Redux slice / Zustand store). The response shape is intentionally flat and self-contained so the frontend can store it directly without transformation.

| Property        | Value                      |
|-----------------|----------------------------|
| Method          | `GET`                      |
| URL             | `/api/user/`               |
| Authentication  | IIS (`REMOTE_USER`)        |
| Authorization   | Any configured role (`app_admin` or `app_viewer`) |
| View            | `api/views/user.py`        |

*Response* `200 OK`
```json
{
    "username": "DOMAIN\\jsmith",
    "roles": ["app_viewer"]
}
```

| Field      | Type       | Description |
|------------|------------|-------------|
| `username` | `string`   | The `REMOTE_USER` identity as provided by IIS (typically `DOMAIN\username`). |
| `roles`    | `string[]` | Application roles derived from AD group membership. One or more of: `app_admin`, `app_viewer`. |

*Response* `401 Unauthorized` — No `REMOTE_USER` header present (IIS auth not configured or request not authenticated).
```json
{
    "detail": "Authentication credentials were not provided.",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

*Response* `403 Forbidden` — User is authenticated but is not a member of any configured AD group.
```json
{
    "detail": "You do not have permission to perform this action.",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

**API Schema** (`GET /api/schema/`)
- Serves the OpenAPI 3 schema generated by `drf-spectacular`.
- Requires IIS authentication (any domain user) but no specific application role.
- Implemented via `api/views/docs.py` wrapper view marked `@authz_authenticated`.

*Response* `401 Unauthorized` — No `REMOTE_USER` header present.
```json
{
    "detail": "Authentication credentials were not provided.",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**API Documentation** (`GET /api/docs/`)
- Serves the interactive Swagger UI for exploring and testing endpoints.
- Requires IIS authentication (any domain user) but no specific application role.
- Implemented via `api/views/docs.py` wrapper view marked `@authz_authenticated`.

*Response* `401 Unauthorized` — No `REMOTE_USER` header present.
```json
{
    "detail": "Authentication credentials were not provided.",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### Logging

*Structured, correlated logging is essential for enterprise operations — incident triage, security audits, and performance analysis all depend on it. The logging design is deliberately minimal: it provides the infrastructure (configuration, correlation, formatting) so that every module added downstream automatically participates in the same logging pipeline without additional setup.*

#### Design Principles

1. **Request-ID correlation** — Every log record automatically includes the `X-Request-ID` generated by `RequestIdMiddleware`. This allows ops teams to trace a single user request across all log lines, middleware layers, adapter calls, and background tasks.
2. **Structured JSON in production** — Production logs are emitted as single-line JSON objects for consistent, machine-parseable output. This simplifies `grep`/`findstr` filtering, integration with Windows Event Forwarding, and future adoption of log aggregation tooling. Development mode uses human-readable console output.
3. **Per-request access log** — Every HTTP request/response pair is logged once with method, path, status code, duration (ms), user identity, and request-ID. This replaces the need for IIS access logs at the Django layer and provides richer context (e.g., resolved username, authorization policy).
4. **Security audit trail** — Authorization denials (401, 403) are logged at `WARNING` level with the username (if available), requested path, and denial reason. This satisfies enterprise security audit requirements.
5. **No sensitive data in logs** — Request bodies, passwords, tokens, and PII beyond the username are never logged. The `REMOTE_USER` header value (corporate username) is the only identity field included.

#### Configuration

Logging is configured via Django's `LOGGING` dict in `config/settings.py`, using Python's standard `logging.config.dictConfig` schema.

| Component | Dev mode (`AUTH_MODE=dev`) | Production (`AUTH_MODE=iis`) |
|-----------|---------------------------|------------------------------|
| Format | Human-readable: `[level] request_id message` | JSON: `{"timestamp", "level", "request_id", "logger", "message"}` |
| Handler | Console (`StreamHandler` to stderr) | Console (`StreamHandler` to stderr, captured by IIS/wfastcgi) |
| Root level | `DEBUG` | `WARNING` |
| `api` logger level | `DEBUG` | `INFO` |
| `django` logger level | `INFO` | `WARNING` |

The JSON formatter is a lightweight custom `logging.Formatter` subclass in `config/logging.py` (no external dependencies). It reads `request_id` from the log record's extras, defaulting to `"-"` when no request context is available (e.g., startup, management commands). Keeping it separate from `settings.py` allows it to be instantiated and tested in isolation without triggering settings validation.

#### Request-ID Threading

The `RequestIdMiddleware` already generates `X-Request-ID` and attaches it to `request.request_id`. To make this available to all loggers without explicit passing:

- The middleware stores the request ID in a **context variable** (`contextvars.ContextVar`), which is thread-safe and async-safe.
- A **logging filter** (`api/middleware/request_id.py::RequestIdFilter`) reads the context variable and injects `request_id` into every log record.
- The filter is attached to all handlers in the `LOGGING` config, so every log line — from middleware, views, services, adapters, or Django internals — automatically carries the correlation ID.

#### Where Logging Happens

| Layer | What is logged | Level |
|-------|---------------|-------|
| `RequestIdMiddleware` | Request received (method, path, user) and response completed (status, duration ms) | `INFO` |
| `AuthorizationMiddleware` | Access denied: 401 (no identity) or 403 (insufficient roles) with username, path, and policy | `WARNING` |
| `api/exceptions.py` | Unhandled exceptions caught by the DRF exception handler (full traceback) | `ERROR` |
| Service layer (future) | Business logic warnings, validation failures | `WARNING` |
| Adapter layer (future) | External call start, response status, retry attempts, failures | `INFO` / `WARNING` / `ERROR` |

#### Log Rotation

The application does not manage log files directly. Both dev and production handlers are `StreamHandler` writing to **stderr** — no `FileHandler` is used. In production under IIS/wfastcgi, stderr output is captured by the wfastcgi process and routed to IIS's logging infrastructure. Log file rotation is managed at the IIS layer via **IIS Manager → Logging → Log File Rollover** (schedule-based or size-based). No Django-side rotation configuration is needed.

#### How This Scales

When downstream teams add new modules (services, adapters, views), they simply use Python's standard `logging.getLogger(__name__)`. The request-ID filter ensures correlation is automatic. No logging boilerplate is required beyond:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Fetched %d records from ERP adapter", count)
```

The hierarchical logger name (`api.adapters.erp`) inherits the `api` logger's level and handlers, so new modules participate in the logging pipeline with zero configuration.

### Exception Handling

*A centralised exception handler ensures every error response has a consistent shape, is logged with full context, and never leaks internal details to the client. This is critical for enterprise CRUD applications where adapter failures, database errors, and validation issues must all be surfaced predictably to the frontend.*

#### Design Principles

1. **Single error envelope** — Every 4xx and 5xx response uses the same JSON shape. The frontend can implement one error-handling path regardless of which endpoint or layer produced the error.
2. **Request-ID in every error response** — The `request_id` field lets frontend teams and support staff quote a correlation ID in bug reports. Ops can then search logs for that exact request.
3. **No internal details leaked** — Stack traces, database errors, and adapter exception messages are logged server-side at `ERROR` level but never included in the response body. The client receives only a safe, generic message for 5xx errors.
4. **DRF integration** — Wired as the custom `EXCEPTION_HANDLER` in `REST_FRAMEWORK` settings. Catches all exceptions raised within DRF views (including serializer validation errors) and exceptions re-raised by middleware.

#### Error Response Contract

All error responses conform to this shape:

```json
{
    "detail": "Human-readable error description.",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `detail` | `string` | A safe, client-facing error message. For validation errors, this may be a structured object with field-level messages (matching DRF's default serializer error shape). |
| `request_id` | `string` | The `X-Request-ID` for this request, for correlation with server logs. |

Standard HTTP status codes and their `detail` values:

| Status | `detail` | When |
|--------|----------|------|
| `400` | Field-specific validation errors (DRF default shape) | Serializer validation failure |
| `401` | `"Authentication credentials were not provided."` | No `REMOTE_USER` / unauthenticated |
| `403` | `"You do not have permission to perform this action."` | Authenticated but lacks required role |
| `404` | `"Not found."` | URL does not match any route, or object lookup failed |
| `405` | `"Method '{method}' not allowed."` | HTTP method not supported by the view |
| `500` | `"An unexpected error occurred."` | Unhandled exception (details logged server-side only) |

#### Implementation

The exception handler lives in `api/exceptions.py` and is a single function:

```python
def api_exception_handler(exc, context):
```

It delegates to DRF's default `exception_handler` first (which handles `APIException` subclasses and Django's `Http404` / `PermissionDenied`). If the default handler returns a response, the handler enriches it with `request_id`. If the default handler returns `None` (unhandled exception), the handler:

1. Logs the full traceback at `ERROR` level with request-ID correlation.
2. Returns a generic `500` response with `"An unexpected error occurred."` and the `request_id`.

This is wired via:
```python
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "api.exceptions.api_exception_handler",
    ...
}
```

#### Middleware Exception Handling

The authorization middleware catches `AuthenticationFailed` and `PermissionDenied` in its own `try/except` and returns `JsonResponse` directly. The middleware runs *before* DRF's view layer, so the DRF exception handler does not apply there. Both paths (middleware and DRF handler) produce the same error envelope shape, including `request_id`.

#### How This Scales

As downstream teams add CRUD views, services, and adapters:

- **Serializer validation errors** (400) are handled automatically by DRF — the exception handler enriches them with `request_id`.
- **Object not found** (`get_object_or_404`) produces a 404 with the standard envelope — no custom handling needed.
- **Adapter failures** (e.g., external API timeout) — adapters raise standard Python exceptions. The exception handler catches them, logs the traceback, and returns a safe 500. For adapter-specific error codes (e.g., "upstream unavailable"), teams can raise custom `APIException` subclasses with appropriate status codes and the handler will format them consistently.
- **Service-layer validation** — services that detect business rule violations can raise `DRF ValidationError` or `PermissionDenied`, and the handler formats them identically to view-level errors.

No per-view `try/except` blocks are needed. The handler is the single funnel for all error responses.

### Caching

*Server-side caching reduces latency, database load, and external API call volume. The caching design provides a production-ready backend configuration and establishes conventions for cache key management that scale as the application adds CRUD endpoints and adapter integrations.*

#### Design Principles

1. **Environment-aware backend** — Development and test environments use Django's `LocMemCache` (zero infrastructure). Production can run with `LocMemCache` initially (no Redis dependency) and can switch to `django-redis` when a Redis service is available. Redis is the recommended production target for shared cache across IIS worker processes and persistence across application restarts.
2. **LDAP group membership is not cached** — AD group changes (additions, removals, disablements) must take immediate effect for security. Every `@authz_roles` request queries LDAP directly. The additional latency is acceptable for this use case. Caching is reserved for application data (adapter responses, service-layer results) where eventual consistency is appropriate.
3. **HTTP cache headers** — Views can declare caching intent via Django's `@cache_control` decorator or `Cache-Control` header manipulation.
4. **Cache key conventions** — A documented naming convention prevents key collisions as the application grows.

#### Cache Backend Configuration

`config/settings.py` selects the cache backend based on the `CACHE_BACKEND` environment variable:

| `CACHE_BACKEND` | Backend | Use case |
|-----------------|---------|----------|
| `redis` | `django_redis.cache.RedisCache` | Production (IIS). Shared across worker processes, survives restarts. |
| `locmem` (default) | `django.core.cache.backends.locmem.LocMemCache` | Development, testing. Zero infrastructure. |

Redis configuration:
```
CACHE_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
```

If Redis is not available in a given production environment, keep:
```
CACHE_BACKEND=locmem
```
This is supported, but cache entries are process-local and not shared across IIS workers.

`django-redis` is available on `conda-forge` and is BSD-licensed (corporate-safe). No additional dependencies beyond Redis itself (typically already available in enterprise environments or trivially installable).

#### Cache Key Conventions

As the application grows to include CRUD operations and multiple adapters, a consistent cache key scheme prevents collisions and makes invalidation predictable:

| Pattern | Example | Used by |
|---------|---------|---------|
| `adapter:{source}:{resource}:{identifier}` | `adapter:erp:invoice:INV-2024-001` | Source adapters (external data) |
| `view:{view_name}:{query_hash}` | `view:order_list:a3f8c1...` | View-level response caching |
| `service:{domain}:{operation}:{params_hash}` | `service:reporting:monthly_summary:b7e2d4...` | Service-layer computed results |

These are conventions, not enforced by framework code. They are documented here so downstream teams adopt them consistently.

#### HTTP Cache Headers

For BFF endpoints serving read-heavy data to frontends:

- **Authenticated endpoints** default to `Cache-Control: private, no-cache` — the browser stores the response but revalidates on every request. This is appropriate for user-specific data (`/api/user/`).
- **Public endpoints** (`/api/health/`) can use `Cache-Control: public, max-age=5` to allow intermediate proxies to cache briefly.
- **Write endpoints** (POST/PUT/DELETE, added by downstream teams) should return `Cache-Control: no-store`.

These are applied via Django's `@cache_control` decorator or set directly on the response. The application does not enforce HTTP cache headers globally — individual views opt in.

#### Cache Invalidation

For CRUD applications, cache invalidation follows a write-through pattern:

1. **Service-layer writes** (create, update, delete) explicitly invalidate related cache keys after a successful database commit.
2. **Adapter-level caching** uses TTL-based expiry. Adapters set a TTL appropriate to the data source's freshness requirements. Manual invalidation is available but optional.

LDAP group membership is not cached and therefore requires no invalidation strategy. AD changes take effect on the next request.

No automatic cache invalidation framework is imposed — this avoids hidden complexity. The convention is explicit: if a service writes data, it deletes the corresponding cache keys.

#### How This Scales

- **Adding a new adapter**: The adapter caches responses using `cache.set(f"adapter:{source}:{resource}:{id}", data, ttl)`. No framework changes needed.
- **Adding CRUD views**: The service layer invalidates relevant cache keys on write. List views can optionally cache their responses with `cache.set(f"view:{name}:{hash}", response, ttl)`.
- **Switching cache backend**: Change `CACHE_BACKEND=redis` and `REDIS_URL` in `.env`. All existing `cache.get()`/`cache.set()` calls work unchanged because they use Django's cache framework API.
- **Multiple cache backends**: If needed (e.g., separate Redis databases for LDAP cache vs. adapter cache), Django supports multiple named caches. Add entries to `CACHES` dict and use `caches['adapter']` in adapter code.

### Automated Testing Strategy (`pytest`)

1. Test Stack
    - `pytest`
    - `pytest-django`
    - `pytest-mock`
    - `responses` or `respx` for external API mocking (use in CI pipelines for integration tests)
    - `pytest-cov` for coverage reporting, targeting 100% unit test coverage
    - `mypy` with `django-stubs` and `djangorestframework-stubs` for static type checking; configured via `mypy.ini`

1. Test Organization
    - The `tests/` directory lives at the root of the backend and mirrors the source code folder structure (for example `tests/api/` covers `api/`, `tests/config/` covers `config/`).
    - Test files are named `test_<module>.py` to match the module they cover (for example `tests/api/test_views.py` covers `api/views.py`).
    - Tests within each file are grouped into classes named after the subject under test (for example `TestHealthView`).
    - `pytest.ini` sets `testpaths = tests` so discovery is explicit and scoped.

1. Authentication & Authorization Testing
    - Backend endpoints correctly read user identity from IIS-provided environment variables or headers (e.g., REMOTE_USER).
    - Backend queries Active Directory via LDAP for group membership and maps to application roles.
    - Group/role mapping from Active Directory is respected for admin-only endpoints.
    - Requests without valid IIS authentication are rejected.

    **Testing IIS/LDAP/AD Authentication and Authorization**
    - IIS authentication is simulated in tests by setting the `REMOTE_USER` header or environment variable in the Django test client.
    - LDAP/AD group membership is mocked by patching the LDAP backend to return the desired group memberships for test users.
    - Pytest fixtures are provided for both `app_admin` and `app_viewer` roles, allowing tests to easily exercise both permission levels on protected routes.
    - These fixtures should be placed in `tests/conftest.py` and used in any test file that needs to verify group-based authorization logic.
    - This approach allows full coverage of authentication and authorization logic without requiring a real IIS or AD server.

### Local Development

*To support local development and testing without requiring IIS, Active Directory, or LDAP, the backend provides a **development mode** that bypasses/mocks authentication and authorization. This enables developers to run the application and all tests locally with minimal setup. Environment variables are loaded from `.env` files using `python-dotenv`. Local development uses `uv` for dependency management (via `pyproject.toml`), while production deployments on Windows use Anaconda (via `environment.yml`). The two manifests describe the same dependency set; `pyproject.toml` is the primary source of truth.*

- A configuration option (environment variable `AUTH_MODE=dev`) is available to switch the backend into development mode.
- In development mode:
    - Authentication middleware injects a mock user identity (e.g., dev_admin or dev_viewer).
    - Authorization middleware assigns the appropriate role (admin or viewer) based on a second environment variable (`DEV_USER_ROLE=admin` or `viewer`).
    - LDAP/AD lookups are skipped or mocked.
- This mode must be used for local development, automated testing, and CI pipelines.

Example .env for Local Development:

```
AUTH_MODE=dev
DEV_USER_IDENTITY=dev_admin
DEV_USER_ROLE=admin
```

**Security Note: Development mode must never be enabled in production or on any externally accessible environment. This is enforced at startup: the application will refuse to start if `AUTH_MODE=dev` is set while `DEBUG=False`. This check runs in the Django `AppConfig.ready()` method to guarantee it cannot be bypassed.**

#### Adding a New Role

The authorization system is designed so that new roles can be introduced without modifying middleware or permissions infrastructure. Only three files need to change:

1. **`api/constants.py`** — Define the role constant and map the AD group:
    ```python
    ROLE_AUDITOR: Final[str] = "app_auditor"
    ROLES = (ROLE_ADMIN, ROLE_VIEWER, ROLE_AUDITOR)

    AD_GROUP_TO_ROLE_MAP: dict[str, str] = {
        "CN=app-admins,OU=Groups,DC=corp,DC=local": ROLE_ADMIN,
        "CN=app-viewers,OU=Groups,DC=corp,DC=local": ROLE_VIEWER,
        "CN=app-auditors,OU=Groups,DC=corp,DC=local": ROLE_AUDITOR,
    }
    ```

2. **`api/views/<view>.py`** — Use the role in a view's `@authz_roles` decorator:
    ```python
    from api.permissions import authz_roles
    from api.constants import ROLE_AUDITOR

    @authz_roles(ROLE_AUDITOR)
    class AuditLogView(APIView):
        ...
    ```

3. **`api/urls.py`** — Wire the new view into the URL configuration.

No changes to `api/permissions.py` or `api/middleware/authorization.py` are required. The middleware resolves roles dynamically from `AD_GROUP_TO_ROLE_MAP` and the `@authz_roles` decorator accepts arbitrary role strings.

#### Configuration Reference

| Environment Variable     | Required | Values                   | Default     | Description |
|--------------------------|----------|--------------------------|-------------|-------------|
| `AUTH_MODE`              | Yes      | `dev`, `iis`             | —           | Authentication mode. `dev` for local development (mocked auth), `iis` for production (IIS/AD). |
| `DEBUG`                  | No       | `True`, `False`          | `False`     | Django debug mode. Must be `False` in production. |
| `DEV_USER_IDENTITY`      | dev only | Any string               | `dev_admin` | Mock username injected in dev mode. |
| `DEV_USER_ROLE`          | dev only | `admin`, `viewer`        | `admin`     | Role assigned to the mock user in dev mode. |
| `LDAP_SERVER_URI`        | iis only | LDAP URI                 | —           | Active Directory LDAP server URI (e.g., `ldap://dc.corp.local`). |
| `LDAP_BASE_DN`           | iis only | Distinguished name       | —           | Base DN for LDAP group searches. |
| `CACHE_BACKEND`          | No       | `locmem`, `redis`        | `locmem`    | Cache backend. Use `redis` in production for cross-process shared cache. |
| `REDIS_URL`              | prod     | Redis URI                | —           | Redis connection URL (e.g., `redis://localhost:6379/0`). Required when `CACHE_BACKEND=redis`. |
| `LOG_LEVEL`              | No       | Python log level name    | `WARNING`   | Root logger level. Overrides the default for production tuning. |
| `LOG_FORMAT`             | No       | `json`, `text`           | `text`      | Log output format. Use `json` in production for structured, machine-parseable output. |
| `ALLOWED_HOSTS`          | Yes      | Comma-separated hosts    | —           | Django `ALLOWED_HOSTS` setting. |
| `CORS_ALLOWED_ORIGINS`   | No       | Comma-separated origins  | —           | Origins permitted for cross-origin requests. Omit if frontend is same-origin. |
| `SECRET_KEY`             | Yes      | String                   | —           | Django secret key. Must be unique and unpredictable in production. |


## Deployment

Deployment targets Windows Server 2022 with IIS serving as the reverse proxy, TLS terminator, and Windows Authentication provider. The Django application runs behind IIS via WSGI using `wfastcgi`.

1. **Install Anaconda & Create Environment**

    Install Anaconda (or Miniconda) on the Windows Server. Create the application environment from the `environment.yml` file:

    ```powershell
    conda env create -f environment.yml
    conda activate django_auth
    ```

    **Sanity check:** Run `python --version` and confirm it outputs `3.14.x`. Run `conda list` and verify `django`, `djangorestframework`, `ldap3`, `drf-spectacular`, `django-cors-headers`, `django-redis`, and `python-dotenv` are all present.

1. **Configure Environment Variables**

    Create a `.env` file in the backend root (or set system environment variables) with production values. At a minimum:

    ```
    AUTH_MODE=iis
    DEBUG=False
    SECRET_KEY=<unique-unpredictable-value>
    ALLOWED_HOSTS=<server-hostname>
    LDAP_SERVER_URI=ldap://dc.corp.local
    LDAP_BASE_DN=DC=corp,DC=local
    LOG_FORMAT=json
    CACHE_BACKEND=locmem
    ```

    Optional (recommended when Redis is available):

    ```
    CACHE_BACKEND=redis
    REDIS_URL=redis://localhost:6379/0
    ```

    Optionally set `CORS_ALLOWED_ORIGINS` if the frontend is served from a different origin.

    **Sanity check:** Run `python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('AUTH_MODE'))"` and confirm it prints `iis`. Verify `DEBUG` is `False` — the application will refuse to start if `AUTH_MODE=dev` with `DEBUG=False`, confirming the safety guard works.

1. **Run Database Migrations**

    Apply Django migrations to initialise the database schema (SQLite by default, or whichever database is configured for the deployment):

    ```powershell
    python manage.py migrate
    ```

    **Sanity check:** Run `python manage.py showmigrations` and confirm all migrations show `[X]` (applied).

1. **Collect Static Files**

    Collect static assets for `drf-spectacular`'s Swagger UI:

    ```powershell
    python manage.py collectstatic --noinput
    ```

    **Sanity check:** Confirm the `STATIC_ROOT` directory exists and contains files (e.g., `drf-spectacular` CSS/JS assets).

1. **Install and Configure IIS**

    Ensure the following IIS features are enabled on the server:

    - Web Server (IIS)
    - Windows Authentication
    - URL Authorization
    - CGI (required by `wfastcgi`)

    ```powershell
    Install-WindowsFeature Web-Server, Web-Windows-Auth, Web-Url-Auth, Web-CGI
    ```

    **Sanity check:** Open IIS Manager and confirm the features appear under the server node. Run `Get-WindowsFeature Web-Server, Web-Windows-Auth, Web-CGI` and verify all show `Installed`.

1. **Register `wfastcgi` with IIS**

    Enable `wfastcgi` to bridge IIS and the Django WSGI application:

    ```powershell
    wfastcgi-enable
    ```

    This registers the Anaconda Python interpreter and `wfastcgi.py` as a FastCGI handler in IIS.

    **Sanity check:** Run `%windir%\system32\inetsrv\appcmd list config -section:system.webServer/fastCgi` and confirm the Python interpreter path and `wfastcgi.py` path appear in the output.

1. **Create the IIS Site**

    Create a new IIS website (or application under an existing site) pointing to the backend directory:

    - **Physical path:** The backend root directory (containing `manage.py`).
    - **Binding:** HTTPS on the appropriate port with a valid TLS certificate.
    - **Application pool:** Create a dedicated app pool, set to `No Managed Code` (since Python handles execution).

    Add a `web.config` to the backend root:

    ```xml
    <?xml version="1.0" encoding="UTF-8"?>
    <configuration>
      <system.webServer>
        <handlers>
          <add name="Python FastCGI"
               path="*"
               verb="*"
               modules="FastCgiModule"
               scriptProcessor="<conda-env-path>\python.exe|<conda-env-path>\Lib\site-packages\wfastcgi.py"
               resourceType="Unspecified" />
        </handlers>
      </system.webServer>
      <appSettings>
        <add key="WSGI_HANDLER" value="config.wsgi.application" />
        <add key="PYTHONPATH" value="<backend-root-path>" />
        <add key="DJANGO_SETTINGS_MODULE" value="config.settings" />
      </appSettings>
    </configuration>
    ```

    Replace `<conda-env-path>` and `<backend-root-path>` with the actual paths.

    **Sanity check:** Browse to `https://<server>/api/health/` from the server itself. It should return `{"status": "ok"}` with a `200` status code. If it errors, check the IIS logs and the Django error output in the `wfastcgi` logs.

1. **Enable Windows Authentication**

    Configure Windows Authentication on the IIS site so that IIS injects the `REMOTE_USER` header:

    - In IIS Manager, select the site → **Authentication**.
    - **Disable** Anonymous Authentication.
    - **Enable** Windows Authentication.

    Ensure the application pool identity has read access to the backend directory.

    > **Note:** With Anonymous Authentication disabled, IIS will challenge *all* requests, including `/api/health/`. The health endpoint is marked `@authz_public` at the Django layer (no `REMOTE_USER` or role required), but IIS will still require Windows Authentication before the request reaches Django. If load balancers or uptime monitors cannot authenticate via Kerberos/NTLM, consider configuring an IIS URL Authorization rule to allow anonymous access to `/api/health/` only.

    **Sanity check:** Browse to `https://<server>/api/user/` from a domain-joined machine. The browser should negotiate Kerberos/NTLM silently and return a `200` with the user's `username` and `roles`. If you receive a `401`, check that Windows Authentication is enabled and Anonymous is disabled. If you receive a `403`, confirm the user is a member of a configured AD group.

1. **Configure LDAP Connectivity**

    Ensure the server can reach the Active Directory LDAP endpoint specified in `LDAP_SERVER_URI`. The application pool identity (or the authenticated user, depending on LDAP bind configuration) must have read access to query group memberships under `LDAP_BASE_DN`.

    **Sanity check:** From the server, run:
    ```powershell
    python -c "from ldap3 import Server, Connection, ALL; s = Server('<LDAP_SERVER_URI>', get_info=ALL); c = Connection(s, auto_bind=True); print(c.result)"
    ```
    Confirm the connection succeeds. Then call `GET /api/user/` as a domain user who belongs to a configured AD group and verify the `roles` array is populated correctly.

1. **Configure HTTPS & TLS**

    Bind a valid TLS certificate to the IIS site. If using an internal CA, ensure the certificate is trusted by client browsers.

    - In IIS Manager, select the site → **Bindings** → Edit the HTTPS binding → Select the certificate.
    - Remove any HTTP bindings (or add a redirect rule from HTTP → HTTPS).

    **Sanity check:** Browse to the site URL via HTTPS and confirm the browser shows a valid certificate (no warnings). Attempt to browse via HTTP and confirm it is either refused or redirected to HTTPS.

1. **Verify End-to-End**

    Perform a full end-to-end validation from a domain-joined client machine:

    | Step | Action | Expected Result |
    |------|--------|-----------------|
    | 1 | `GET /api/health/` | `200 OK` — `{"status": "ok"}` (no authentication required) |
    | 2 | `GET /api/user/` (unauthenticated / anonymous) | `401 Unauthorized` |
    | 3 | `GET /api/user/` (domain user in configured AD group) | `200 OK` — `{"username": "DOMAIN\\user", "roles": [...]}` |
    | 4 | `GET /api/user/` (domain user not in any configured group) | `403 Forbidden` |
    | 5 | `GET /api/docs/` (unauthenticated) | `401 Unauthorized` |
    | 6 | `GET /api/docs/` (any domain user) | Swagger UI loads successfully |
    | 7 | `GET /api/schema/` (unauthenticated) | `401 Unauthorized` |
    | 8 | `GET /api/schema/` (any domain user) | OpenAPI 3 JSON schema returned |

    **Sanity check:** All eight checks pass. Review the IIS access logs and confirm requests are logged with the expected HTTP status codes and authenticated usernames.

---

[**Back to Top**](#django-authentication--authorization)

