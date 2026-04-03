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
ALLOWED_HOSTS: list[str] = [
    host.strip() for host in ALLOWED_HOSTS_RAW.split(",") if host.strip()
]
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "api.middleware.request_id.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "api.middleware.authentication.AuthenticationMiddleware",
    "api.middleware.enforcement.DecoratorEnforcementMiddleware",
    "api.middleware.authorization.AuthorizationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS_RAW: str = os.getenv("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS: list[str] = [
    origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()
]
CORS_ALLOW_ALL_ORIGINS = DEBUG

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
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Django Authentication & Authorization API",
    "DESCRIPTION": "BFF API for IIS/AD-backed authentication and authorization.",
    "VERSION": "0.1.0",
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "django-auth-cache",
    }
}

CSRF_TRUSTED_ORIGINS: list[str] = []

LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text").strip().lower()
LOG_LEVEL: str = (
    os.getenv("LOG_LEVEL", "DEBUG" if AUTH_MODE == "dev" else "WARNING").strip().upper()
)


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
