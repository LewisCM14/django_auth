"""Unit tests for Windows auth token resolution helpers."""

from __future__ import annotations

import pytest

from api.middleware import authentication


@pytest.mark.parametrize(
    ("token", "expected"),
    [("0x10", 16), ("10", 16), ("", None), ("not-hex", None)],
)
def test_parse_token_handle(token: str, expected: int | None) -> None:
    assert authentication._parse_token_handle(token) == expected


def test_load_pywin32_modules_returns_none_on_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authentication.sys, "platform", "linux")
    assert authentication._load_pywin32_modules() is None


def test_load_pywin32_modules_returns_none_when_packages_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(authentication.sys, "platform", "win32")
    monkeypatch.setattr(authentication.importlib.util, "find_spec", lambda _: None)
    assert authentication._load_pywin32_modules() is None


def test_resolve_handles_os_error_during_impersonation(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = authentication.WindowsAuthIdentityResolver()

    class BrokenSecurity:
        def ImpersonateLoggedOnUser(self, handle: int) -> None:
            raise OSError("boom")

        def RevertToSelf(self) -> None:
            raise AssertionError("should not revert when impersonation never started")

    class FakeApi:
        def __init__(self) -> None:
            self.closed: list[int] = []

        def GetUserName(self) -> str:
            return "DOMAIN\\ignored"

        def CloseHandle(self, handle: int) -> None:
            self.closed.append(handle)

    fake_api = FakeApi()
    monkeypatch.setattr(
        authentication, "_load_pywin32_modules", lambda: (fake_api, BrokenSecurity())
    )

    assert resolver.resolve("0x10") is None
    assert fake_api.closed == [16]


def test_resolve_success_with_revert_and_close_errors_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = authentication.WindowsAuthIdentityResolver()

    class FakeSecurity:
        def ImpersonateLoggedOnUser(self, handle: int) -> None:
            return None

        def RevertToSelf(self) -> None:
            raise OSError("cannot revert")

    class FakeApi:
        def GetUserName(self) -> str:
            return "DOMAIN\\ok"

        def CloseHandle(self, handle: int) -> None:
            raise OSError("cannot close")

    monkeypatch.setattr(
        authentication, "_load_pywin32_modules", lambda: (FakeApi(), FakeSecurity())
    )
    assert resolver.resolve("0x20") == "DOMAIN\\ok"


def test_resolve_returns_none_when_modules_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = authentication.WindowsAuthIdentityResolver()
    monkeypatch.setattr(authentication, "_load_pywin32_modules", lambda: None)
    assert resolver.resolve("0x10") is None


def test_resolve_returns_none_for_blank_header() -> None:
    resolver = authentication.WindowsAuthIdentityResolver()
    assert resolver.resolve("  ") is None
