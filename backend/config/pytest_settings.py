"""Test settings that preload the committed env example before base settings."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.example", override=True)

from . import settings as _settings  # noqa: E402 - load_dotenv must run first so settings sees .env.example

for name, value in vars(_settings).items():
    if name.isupper():
        globals()[name] = value

# Test client requests are HTTP by default; disable redirect enforcement so
# middleware/authz tests can exercise application behavior directly.
SECURE_SSL_REDIRECT = False

del _settings
