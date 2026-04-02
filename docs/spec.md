# Django Authentication & Authorization

*A minimal Django web application designed for use within corporate enterprise to be deployed specifically to Windows servers that uses IIS for Authentication and Activate Directory for Authorization. Able to scale and extend for a multitude of use cases by utilizing the Adapter pattern.*

## Table of Contents
- [Requirement](#requirement)
- [Design](#design)
    - [Application Architecture Diagram](#application-architecture-diagram)
    - [Workflow](#workflow)
    - [Structure](#structure)
    - [Endpoints](#endpoints)
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
    - LDAP group membership results must be cached using Django's cache framework with a configurable TTL (`LDAP_CACHE_TTL`) to avoid querying AD on every request.
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
    MW_AuthZ -- "LDAP lookup\n(cached, @authz_roles only)" --> AD
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
    - Uses `ldap3` library to query Active Directory for group membership, with results cached via Django's cache framework (configurable TTL) to avoid querying AD on every request.
    - Maps AD group membership to Django user roles for authorization (e.g., admin access).
    - Enforces explicit per-view authorization policy declaration using permission decorators in `api/permissions.py`:
        - `@authz_public` — no authentication or authorization required (e.g. health probes)
        - `@authz_authenticated` — IIS authentication required, no specific role (e.g. API docs)
        - `@authz_roles(...)` — IIS authentication required with one or more specific roles
    - Every view must declare exactly one of these decorators. Views that omit a decorator raise `ImproperlyConfigured` at request time. There are no default permissions — future developers must explicitly set authorization at the view level.
    - LDAP group membership is only queried for views decorated with `@authz_roles(...)`. Views using `@authz_public` or `@authz_authenticated` never trigger an LDAP lookup.
    - Strict mode: routed endpoints must be implemented in `api.views`. Third-party endpoints (for example drf-spectacular schema/docs) must be exposed through wrapper views in `api.views` and decorated explicitly.

1. Service Layer
    - Implements business workflows.
    - Orchestrates internal DB operations and/or external source reads.
    - Transforms and normalizes external/internal payloads into canonical response objects for the UI.

1. Source Adapter Layer
    - One adapter per external source.
    - Handles source-specific authentication, request/response contracts, retries, and error mapping.
    - Performs minimal parsing: converts raw responses to native Python structures, handles protocol-level details, and validates required fields, but does not apply business rules or normalization (handled in the application & mapping layer).

1. Persistence Layer (`Django ORM`)
    - Uses Django models and migrations for internal schema evolution.
    - Keeps write operations limited to app-owned internal tables.

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

    V -->|Raw request data| S
    S -->|Validated data| BL
    BL -->|Invoke| NORM
    NORM -->|Fetch/Join| AD
    AD -->|Raw/parsed data| NORM
    BL -->|DB ops| DB
    NORM -->|Canonical response| S
    S -->|Serialize output| V
```

```mermaid
---
title: Authentication & Authorization — Level 1
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

    User->>FE: Interact with application
    FE->>IIS: HTTPS request (Kerberos/NTLM)
    IIS->>IIS: Windows Authentication
    alt Authentication fails at IIS
        IIS-->>FE: 401 Unauthorized
    else Authentication succeeds
        IIS->>RID: WSGI request + REMOTE_USER header
        RID->>RID: Generate & attach X-Request-ID
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
                AuthZ-->>FE: 401 Unauthorized
            else Authenticated
                AuthZ->>View: Forward request (no role check)
            end
        else @authz_roles(...) (e.g. /api/user/)
            AuthZ->>AuthZ: Verify REMOTE_USER present
            alt Not authenticated
                AuthZ-->>FE: 401 Unauthorized
            else Authenticated
                AuthZ->>Cache: Lookup cached group membership
                alt Cache hit
                    Cache-->>AuthZ: Cached roles
                else Cache miss
                    AuthZ->>AD: LDAP query (user group membership)
                    AD-->>AuthZ: Group list
                    AuthZ->>AuthZ: Map AD groups → app roles
                    AuthZ->>Cache: Store roles (TTL = LDAP_CACHE_TTL)
                end

                alt No matching roles
                    AuthZ-->>FE: 403 Forbidden
                else Roles match
                    AuthZ->>AuthZ: Attach roles to request.user
                    AuthZ->>View: Forward authorized request
                end
            end
        end

        View->>View: Process & build response
        View-->>FE: 200 OK (response payload)
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

Returns the authenticated user's identity and assigned roles. Requires a valid `REMOTE_USER` (provided by IIS in production or injected by dev-mode middleware locally). The authorization middleware resolves the user's AD group memberships (via LDAP, cached) and maps them to application roles before the request reaches this view.

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
    "detail": "Authentication credentials were not provided."
}
```

*Response* `403 Forbidden` — User is authenticated but is not a member of any configured AD group.
```json
{
    "detail": "You do not have permission to perform this action."
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
    "detail": "Authentication credentials were not provided."
}
```

**API Documentation** (`GET /api/docs/`)
- Serves the interactive Swagger UI for exploring and testing endpoints.
- Requires IIS authentication (any domain user) but no specific application role.
- Implemented via `api/views/docs.py` wrapper view marked `@authz_authenticated`.

*Response* `401 Unauthorized` — No `REMOTE_USER` header present.
```json
{
    "detail": "Authentication credentials were not provided."
}
```

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
| `LDAP_CACHE_TTL`         | No       | Integer (seconds)        | `300`       | TTL for cached LDAP group membership results. |
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

    **Sanity check:** Run `python --version` and confirm it outputs `3.14.x`. Run `conda list` and verify `django`, `djangorestframework`, `ldap3`, `drf-spectacular`, `django-cors-headers`, and `python-dotenv` are all present.

1. **Configure Environment Variables**

    Create a `.env` file in the backend root (or set system environment variables) with production values. At a minimum:

    ```
    AUTH_MODE=iis
    DEBUG=False
    SECRET_KEY=<unique-unpredictable-value>
    ALLOWED_HOSTS=<server-hostname>
    LDAP_SERVER_URI=ldap://dc.corp.local
    LDAP_BASE_DN=DC=corp,DC=local
    LDAP_CACHE_TTL=300
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

