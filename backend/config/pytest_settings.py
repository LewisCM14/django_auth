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

del _settings
