"""Django settings module for the authentication service.

Loads configuration from environment variables (.env file) and validates
required settings at startup. Supports two authentication modes: 'dev' for
local development and 'iis' for Windows IIS deployment.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from api.validation import (
    validate_allowed_hosts,
    validate_api_version,
    validate_cors_allowed_origins,
    validate_ldap_base_dn,
    validate_ldap_server_uri,
    validate_log_format,
    validate_log_level,
)


BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

AUTH_MODE: str = os.getenv("AUTH_MODE", "dev").strip().lower()
if AUTH_MODE not in {"dev", "iis"}:
    raise ImproperlyConfigured("AUTH_MODE must be either 'dev' or 'iis'.")

SECRET_KEY: str = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY is required.")

DEBUG: bool = os.getenv("DEBUG", "False").strip().lower() == "true"

ALLOWED_HOSTS_RAW: str = os.getenv("ALLOWED_HOSTS", "")
ALLOWED_HOSTS: list[str] = validate_allowed_hosts(ALLOWED_HOSTS_RAW)
if AUTH_MODE == "iis" and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS is required when AUTH_MODE='iis'.")
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Apps required by the codebase:
# - auth/contenttypes: Django User model used by custom auth middleware
# - staticfiles/templates/sidecar: drf-spectacular Swagger UI HTML and bundled assets
# - rest_framework/drf_spectacular/corsheaders/api: core API stack
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "corsheaders",
    "api",
]

# Apps required middleware: order matters for correct authentication and authorization behavior.
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "api.middleware.request_id.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "api.middleware.content_security_policy.ContentSecurityPolicyMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "api.middleware.authentication.AuthenticationMiddleware",
    "api.middleware.enforcement.DecoratorEnforcementMiddleware",
    "api.middleware.authorization.AuthorizationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# Django templates are only used to render Swagger UI HTML.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "api" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        # Django's built-in auth app persists User rows for REMOTE_USER identities.
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Required so Swagger UI assets can be served in development and collected in deployment.
STATIC_URL = "static/"

# Avoid implicit primary-key defaults on ORM models
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS_RAW: str = os.getenv("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS: list[str] = validate_cors_allowed_origins(
    CORS_ALLOWED_ORIGINS_RAW
)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# Release version surfaced by /api/health/ and OpenAPI docs.
# Tagged-release overwrite this placeholder in .env.
API_VERSION: str = validate_api_version(
    os.getenv("API_VERSION", "APP_VERSION").strip() or "APP_VERSION"
)

# LDAP settings are required for IIS mode; optional for dev mode.
# In IIS mode, query_ldap_groups uses these to look up user group membership.
LDAP_SERVER_URI_RAW: str = os.getenv("LDAP_SERVER_URI", "").strip()
LDAP_BASE_DN_RAW: str = os.getenv("LDAP_BASE_DN", "").strip()

LDAP_SERVER_URI: str = (
    validate_ldap_server_uri(LDAP_SERVER_URI_RAW) if LDAP_SERVER_URI_RAW else ""
)
LDAP_BASE_DN: str = validate_ldap_base_dn(LDAP_BASE_DN_RAW) if LDAP_BASE_DN_RAW else ""

if AUTH_MODE == "iis" and (not LDAP_SERVER_URI or not LDAP_BASE_DN):
    raise ImproperlyConfigured(
        "LDAP_SERVER_URI and LDAP_BASE_DN are required when AUTH_MODE='iis'."
    )

# Security headers and cookie flags are explicit so production deployments
# remain hardened even if the hosting layer omits defaults.
SECURE_PROXY_SSL_HEADER: tuple[str, str] | None = (
    ("HTTP_X_FORWARDED_PROTO", "https") if AUTH_MODE == "iis" else None
)
SECURE_SSL_REDIRECT: bool = False
SECURE_HSTS_SECONDS: int = 31536000 if AUTH_MODE == "iis" else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = AUTH_MODE == "iis"
SECURE_HSTS_PRELOAD: bool = False
SECURE_CONTENT_TYPE_NOSNIFF: bool = True
SECURE_REFERRER_POLICY: str = "same-origin"
X_FRAME_OPTIONS: str = "DENY"
SESSION_COOKIE_SECURE: bool = AUTH_MODE == "iis"
SESSION_COOKIE_HTTPONLY: bool = True
SESSION_COOKIE_SAMESITE: str = "Lax"
CSRF_COOKIE_SECURE: bool = AUTH_MODE == "iis"
CSRF_COOKIE_HTTPONLY: bool = True
CSRF_COOKIE_SAMESITE: str = "Lax"
CONTENT_SECURITY_POLICY: str = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'none'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "script-src 'self'; "
    "style-src 'self'"
)

# DRF is configured as a thin transport layer. Authentication/authorization are
# enforced in middleware so every endpoint follows the same project-specific policy.
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "api.exceptions.api_exception_handler",
    # Authentication and authorization are handled entirely by middleware
    # (api.middleware.authentication and api.middleware.authorization).
    # DRF's own auth/permission system is deliberately disabled so that
    # every view must declare an explicit policy via @authz_public or
    # @authz_roles(...).  AllowAny prevents DRF from rejecting requests
    # before the middleware has a chance to enforce the view-level policy.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# Metadata surfaced by drf-spectacular at /api/schema/ and /api/docs/.
SPECTACULAR_SETTINGS = {
    "TITLE": "Django Authentication & Authorization API",
    "DESCRIPTION": "BFF API for IIS/AD-backed authentication and authorization.",
    "VERSION": API_VERSION,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
}

# Single-process cache backend used for throttling and app-level caching.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "django-auth-cache",
    }
}

LOG_FORMAT: str = validate_log_format(os.getenv("LOG_FORMAT", "text"))
LOG_LEVEL: str = validate_log_level(
    os.getenv("LOG_LEVEL", "DEBUG" if AUTH_MODE == "dev" else "WARNING")
)


# Logging is emitted to stderr so local runs and IIS/wfastcgi can capture the same stream.
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "api.middleware.request_id.RequestIdFilter",
        },
    },
    "formatters": {
        "json": {
            "()": "config.logging.JsonFormatter",
        },
        "text": {
            "format": "[{levelname}] {request_id} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "filters": ["request_id"],
            "formatter": "json" if LOG_FORMAT == "json" else "text",
        },
    },
    "loggers": {
        "api": {
            "level": "DEBUG" if AUTH_MODE == "dev" else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "django.server": {
            "handlers": [],
            "propagate": False,
        },
        "django": {
            "level": "INFO" if AUTH_MODE == "dev" else "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
    },
    "root": {
        "level": LOG_LEVEL,
        "handlers": ["console"],
    },
}
