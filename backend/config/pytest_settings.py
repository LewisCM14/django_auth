"""Test settings that preload the committed env example before base settings."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.example", override=True)

from .settings import *  # noqa: E402,F403
