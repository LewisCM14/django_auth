"""Tests for the user information endpoint."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client

from api.constants import ADMIN_AD_GROUP, VIEWER_AD_GROUP
from api.views.user import UserView


class TestUserView:
    """Tests for `GET /api/user/` and method constraints."""

    @pytest.mark.django_db
    def test_admin_user_returns_200(self, admin_client: Client) -> None:
        """Admin client receives HTTP 200 from user endpoint."""
        response = admin_client.get("/api/user/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_admin_user_response_contains_username(self, admin_client: Client) -> None:
        """Admin response includes expected username."""
        response = admin_client.get("/api/user/")
        assert response.status_code == 200
        assert response.json()["username"] == "DOMAIN\\admin_user"

    @pytest.mark.django_db
    def test_admin_user_response_contains_admin_role(
        self, admin_client: Client
    ) -> None:
        """Admin response includes app_admin role."""
        response = admin_client.get("/api/user/")
        assert response.status_code == 200
        assert "app_admin" in response.json()["roles"]

    @pytest.mark.django_db
    def test_viewer_user_returns_200(self, viewer_client: Client) -> None:
        """Viewer client receives HTTP 200 from user endpoint."""
        response = viewer_client.get("/api/user/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_viewer_user_response_contains_viewer_role(
        self, viewer_client: Client
    ) -> None:
        """Viewer response includes app_viewer role."""
        response = viewer_client.get("/api/user/")
        assert response.status_code == 200
        assert "app_viewer" in response.json()["roles"]

    @pytest.mark.django_db
    def test_user_with_two_ad_groups_returns_both_roles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User in admin and viewer AD groups receives both application roles."""

        def mock_query_ldap_groups(username: str) -> list[str]:
            if username == "DOMAIN\\power_user":
                return [ADMIN_AD_GROUP, VIEWER_AD_GROUP]
            return []

        monkeypatch.setattr(
            "api.middleware.authorization.query_ldap_groups",
            mock_query_ldap_groups,
        )
        monkeypatch.setattr(
            "api.middleware.authentication.WindowsAuthIdentityResolver.resolve",
            lambda _self, _token: "DOMAIN\\power_user",
        )
        monkeypatch.setenv("AUTH_MODE", "iis")

        client = Client()
        client.defaults["HTTP_X_IIS_WINDOWSAUTHTOKEN"] = "0xD44"

        response = client.get("/api/user/")

        assert response.status_code == 200
        payload = response.json()
        assert payload["username"] == "DOMAIN\\power_user"
        assert payload["roles"] == ["app_admin", "app_viewer"]

    @pytest.mark.django_db
    def test_user_response_has_private_cache_header(self, admin_client: Client) -> None:
        """GET /api/user/ returns private no-cache directives."""
        response = admin_client.get("/api/user/")
        cache_control = response.headers.get("Cache-Control", "")
        assert "private" in cache_control
        assert "no-cache" in cache_control
        assert "default-src 'none'" in response.headers.get(
            "Content-Security-Policy", ""
        )

    def test_unauthenticated_returns_401(self, unauthenticated_client: Client) -> None:
        """Unauthenticated request is rejected with 401."""
        response = unauthenticated_client.get("/api/user/")
        assert response.status_code == 401

    @pytest.mark.django_db
    def test_unauthorized_returns_403(self, unauthorized_client: Client) -> None:
        """Authenticated user without mapped roles is rejected with 403 JSON."""
        response = unauthorized_client.get("/api/user/")
        assert response.status_code == 403
        assert (
            response.json()["detail"]
            == "You do not have permission to perform this action."
        )

    @pytest.mark.django_db
    def test_method_not_allowed_post(self, admin_client: Client) -> None:
        """POST is not allowed on user endpoint."""
        response = admin_client.post("/api/user/")
        assert response.status_code == 405

    @pytest.mark.django_db
    def test_method_not_allowed_put(self, admin_client: Client) -> None:
        """PUT is not allowed on user endpoint."""
        response = admin_client.put("/api/user/")
        assert response.status_code == 405

    @pytest.mark.django_db
    def test_method_not_allowed_delete(self, admin_client: Client) -> None:
        """DELETE is not allowed on user endpoint."""
        response = admin_client.delete("/api/user/")
        assert response.status_code == 405

    @pytest.mark.django_db
    def test_user_returns_429_when_throttled(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second rapid request returns 429 with standard error envelope."""
        cache.clear()
        monkeypatch.setattr(UserView, "_throttle_rate", "1/minute")

        first = admin_client.get("/api/user/")
        second = admin_client.get("/api/user/")

        assert first.status_code == 200
        assert second.status_code == 429
        payload = second.json()
        assert "throttled" in payload["detail"].lower()
        assert "request_id" in payload

    @pytest.mark.django_db
    def test_user_throttle_includes_retry_after(
        self, admin_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """429 response includes a Retry-After header."""
        cache.clear()
        monkeypatch.setattr(UserView, "_throttle_rate", "1/minute")

        admin_client.get("/api/user/")
        response = admin_client.get("/api/user/")

        assert response.status_code == 429
        assert response["Retry-After"].isdigit()
