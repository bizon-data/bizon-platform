"""Tests for custom source name validation and auth exemptions."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from bizon_platform.api.auth import optional_auth
from bizon_platform.api.routes.custom_sources import _source_dir


class TestSourceDir:
    """Tests for _source_dir."""

    @pytest.mark.parametrize("name", ["hubspot", "my_source", "Source2"])
    def test_valid_names(self, name, tmp_path):
        with patch("bizon_platform.api.routes.custom_sources.settings") as settings:
            settings.custom_sources_dir = str(tmp_path)
            assert _source_dir(name) == str(tmp_path / name)

    @pytest.mark.parametrize("name", ["..", "../etc", "a/b", "a\\b", "", "my-source", "x.py"])
    def test_rejects_unsafe_names(self, name):
        with pytest.raises(HTTPException) as exc:
            _source_dir(name)
        assert exc.value.status_code == 400


def _request(path: str) -> MagicMock:
    request = MagicMock()
    request.url.path = path
    return request


class TestOptionalAuth:
    """Tests for the unauthenticated path allowlist."""

    def test_webhook_skips_basic_auth(self):
        with patch("bizon_platform.api.auth.settings") as settings:
            settings.admin_password = "secret"
            asyncio.run(optional_auth(_request("/api/custom-sources/git-sync/webhook"), None))

    def test_other_paths_still_require_auth(self):
        with patch("bizon_platform.api.auth.settings") as settings:
            settings.admin_password = "secret"
            with pytest.raises(HTTPException) as exc:
                asyncio.run(optional_auth(_request("/api/custom-sources/git-sync"), None))
            assert exc.value.status_code == 401

    def test_valid_credentials_accepted(self):
        with patch("bizon_platform.api.auth.settings") as settings:
            settings.admin_password = "secret"
            credentials = HTTPBasicCredentials(username="admin", password="secret")
            asyncio.run(optional_auth(_request("/api/pipelines"), credentials))
