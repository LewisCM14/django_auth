"""Tests for the user information endpoint."""

from __future__ import annotations

import pytest
from django.test import Client


@pytest.mark.django_db
class TestUserView:
    """Tests for `GET /api/user/` and method constraints."""

    def test_admin_user_returns_200(self, admin_client: Client) -> None:
        """Admin client receives HTTP 200 from user endpoint."""
        response = admin_client.get("/api/user/")
        assert response.status_code == 200

    def test_admin_user_response_contains_username(self, admin_client: Client) -> None:
        """Admin response includes expected username."""
        response = admin_client.get("/api/user/")
        assert response.status_code == 200
        assert response.json()["username"] == "DOMAIN\\admin_user"

    def test_admin_user_response_contains_admin_role(
        self, admin_client: Client
    ) -> None:
        """Admin response includes app_admin role."""
        response = admin_client.get("/api/user/")
        assert response.status_code == 200
        assert "app_admin" in response.json()["roles"]

    def test_viewer_user_returns_200(self, viewer_client: Client) -> None:
        """Viewer client receives HTTP 200 from user endpoint."""
        response = viewer_client.get("/api/user/")
        assert response.status_code == 200

    def test_viewer_user_response_contains_viewer_role(
        self, viewer_client: Client
    ) -> None:
        """Viewer response includes app_viewer role."""
        response = viewer_client.get("/api/user/")
        assert response.status_code == 200
        assert "app_viewer" in response.json()["roles"]

    def test_unauthenticated_returns_401(self, unauthenticated_client: Client) -> None:
        """Unauthenticated request is rejected with 401."""
        response = unauthenticated_client.get("/api/user/")
        assert response.status_code == 401

    def test_unauthorized_returns_403(self, unauthorized_client: Client) -> None:
        """Authenticated user without mapped roles is rejected with 403 JSON."""
        response = unauthorized_client.get("/api/user/")
        assert response.status_code == 403
        assert response.json() == {
            "detail": "You do not have permission to perform this action."
        }

    def test_method_not_allowed_post(self, admin_client: Client) -> None:
        """POST is not allowed on user endpoint."""
        response = admin_client.post("/api/user/")
        assert response.status_code == 405

    def test_method_not_allowed_put(self, admin_client: Client) -> None:
        """PUT is not allowed on user endpoint."""
        response = admin_client.put("/api/user/")
        assert response.status_code == 405

    def test_method_not_allowed_delete(self, admin_client: Client) -> None:
        """DELETE is not allowed on user endpoint."""
        response = admin_client.delete("/api/user/")
        assert response.status_code == 405
