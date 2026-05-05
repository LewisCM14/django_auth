# Django Authentication & Authorization

*A minimal Django web application designed for use within corporate enterprise to be deployed specifically to Windows servers that uses IIS for Authentication and Activate Directory for Authorization. Able to scale and extend for a multitude of use cases by utilizing the Adapter pattern.*

## Getting Started

### 1) Enter the backend directory

```bash
cd backend
```

### 2) Install dependencies

```bash
uv sync
```

### 3) Configure environment variables

Create a local `.env` file in `backend/` (or copy from `.env.example`) and set at least:

```env
AUTH_MODE=dev
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DEV_USER_IDENTITY=dev_admin
DEV_USER_ROLE=app_admin,app_viewer
ADMIN_AD_GROUP=CN=app-admins,OU=Groups,DC=corp,DC=local
VIEWER_AD_GROUP=CN=app-viewers,OU=Groups,DC=corp,DC=local
```

Keep `ADMIN_AD_GROUP` and `VIEWER_AD_GROUP` populated in every environment. Dev mode does not query LDAP, but the values are validated at startup so deployment-specific `.env` files stay complete.
`DEV_USER_ROLE` accepts one or more comma-separated canonical roles (for example `app_admin,app_viewer`).

### 4) Apply migrations

```bash
uv run python manage.py migrate
```

### 5) Run the development server

```bash
uv run python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/`.

## API Documentation

With the server running:

- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`
- Health check: `http://127.0.0.1:8000/api/health/`

## Mimic Different Roles Locally

Use development mode to switch the effective user role without IIS/AD.

### Admin role

Set in `backend/.env`:

```env
AUTH_MODE=dev
DEV_USER_IDENTITY=dev_admin
DEV_USER_ROLE=app_admin
```

### Viewer role

Set in `backend/.env`:

```env
AUTH_MODE=dev
DEV_USER_IDENTITY=dev_viewer
DEV_USER_ROLE=app_viewer
```

### Admin + viewer roles

Set in `backend/.env`:

```env
AUTH_MODE=dev
DEV_USER_IDENTITY=dev_power_user
DEV_USER_ROLE=app_admin,app_viewer
```

### Apply changes

After changing role values, restart the dev server:

```bash
cd backend
uv run python manage.py runserver
```

### Verify active role

Call the user endpoint:

```bash
curl http://127.0.0.1:8000/api/user/
```

Expected examples:

- Admin mode: `{"username": "dev_admin", "roles": ["app_admin"]}`
- Viewer mode: `{"username": "dev_viewer", "roles": ["app_viewer"]}`
- Admin + viewer mode: `{"username": "dev_power_user", "roles": ["app_admin", "app_viewer"]}`

## Quality Checks

Run all quality commands from the backend directory:

```bash
cd backend
```

### 1) Linting

```bash
uv run ruff check . --fix
```

### 2) Formatting

```bash
uv run ruff format .
```

### 3) Type Checking

Type checking is configured with MyPy in strict mode:

```bash
uv run mypy .
```

### 4) Tests

Run the full test suite:

```bash
uv run pytest
```
> Coverage is configured in `pytest.ini` and runs automatically — a terminal summary and `coverage.xml` (for SonarQube) are produced on every run.