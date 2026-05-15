"""
Tests for configuration module
"""

import pytest
import os
from pathlib import Path

from src.config import AtlassianConfig, ReportConfig, ExportConfig, Config


class TestAtlassianConfig:
    """Test AtlassianConfig class"""

    def test_create_config(self):
        """Test creating AtlassianConfig"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )

        assert config.url == "https://test.atlassian.net"
        assert config.username == "test@example.com"
        assert config.api_token == "test-token"
        assert config.project_keys == ["TEST"]

    def test_default_field_values(self):
        """Test default values for optional fields"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
        )

        assert config.project_keys is None
        assert config.enable_cache is True
        assert config.cache_dir == ".cache"
        assert config.max_workers == 8

    def test_validate_valid_config(self):
        """Test validation with valid config"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="valid-token-123",
            project_keys=["TEST"]
        )

        assert config.validate() is True

    def test_validate_invalid_url(self):
        """Test validation with invalid URL"""
        config = AtlassianConfig(
            url="invalid-url",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_URL"):
            config.validate()

    def test_validate_invalid_url_scheme(self):
        """Test validate raises ValueError for invalid URL scheme"""
        config = AtlassianConfig(
            url="ftp://confluence.example.com",
            username="admin@example.com",
            api_token="token123456",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_URL"):
            config.validate()

    def test_validate_empty_url(self):
        """Test validate raises ValueError for empty URL"""
        config = AtlassianConfig(
            url="", username="admin@example.com", api_token="token123456"
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_URL"):
            config.validate()

    def test_validate_invalid_username(self):
        """Test validation with invalid username (no @ symbol)"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="invalid",
            api_token="test-token",
            project_keys=["TEST"]
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_USERNAME"):
            config.validate()

    def test_validate_empty_username(self):
        """Test validate raises ValueError for empty username"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="",
            api_token="token123456",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_USERNAME"):
            config.validate()

    def test_validate_empty_api_token(self):
        """Test validate raises ValueError for empty api_token"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="admin@example.com",
            api_token="",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_API_TOKEN"):
            config.validate()

    def test_validate_short_api_token(self):
        """Test validate raises ValueError for api_token shorter than 10 chars"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="admin@example.com",
            api_token="short",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_API_TOKEN"):
            config.validate()

    def test_validate_no_project_keys(self):
        """Test validation with no project keys (should be valid - will fetch all)"""
        config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token-123456",
            project_keys=None
        )

        assert config.validate() is True

    def test_from_env_loads_atlassian_vars(self, monkeypatch):
        """Test from_env loads ATLASSIAN_* env vars"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://test.atlassian.net")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "user@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token-12345678")

        config = AtlassianConfig.from_env()

        assert config.url == "https://test.atlassian.net"
        assert config.username == "user@example.com"
        assert config.api_token == "token-12345678"

    def test_from_env_loads_project_keys(self, monkeypatch):
        """Test from_env loads project keys"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://test.atlassian.net")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "user@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token-12345678")
        monkeypatch.setenv("ATLASSIAN_PROJECT_KEYS", "PROJ1,PROJ2")

        config = AtlassianConfig.from_env()

        assert config.project_keys == ["PROJ1", "PROJ2"]

    def test_from_env_strips_trailing_slashes(self, monkeypatch):
        """Test that from_env normalizes URL by stripping trailing slashes"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://test.atlassian.net///")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        config = AtlassianConfig.from_env()

        assert config.url == "https://test.atlassian.net"

    def test_from_env_strips_whitespace(self, monkeypatch):
        """Test that from_env strips leading/trailing whitespace from values"""
        monkeypatch.setenv("ATLASSIAN_URL", "  https://test.atlassian.net  ")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "  admin@example.com  ")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "  token123456  ")

        config = AtlassianConfig.from_env()

        assert config.url == "https://test.atlassian.net"
        assert config.username == "admin@example.com"
        assert config.api_token == "token123456"

    def test_from_env_missing_url(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_URL is missing"""
        monkeypatch.delenv("ATLASSIAN_URL", raising=False)
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_URL"):
            AtlassianConfig.from_env()

    def test_from_env_empty_url(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_URL is empty"""
        monkeypatch.setenv("ATLASSIAN_URL", "")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_URL"):
            AtlassianConfig.from_env()

    def test_from_env_whitespace_only_url(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_URL is whitespace only"""
        monkeypatch.setenv("ATLASSIAN_URL", "   ")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_URL"):
            AtlassianConfig.from_env()

    def test_from_env_missing_username(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_USERNAME is missing"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://test.atlassian.net")
        monkeypatch.delenv("ATLASSIAN_USERNAME", raising=False)
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_USERNAME"):
            AtlassianConfig.from_env()

    def test_from_env_missing_api_token(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_API_TOKEN is missing"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://test.atlassian.net")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.delenv("ATLASSIAN_API_TOKEN", raising=False)

        with pytest.raises(ValueError, match="ATLASSIAN_API_TOKEN"):
            AtlassianConfig.from_env()

    def test_from_env_invalid_url_scheme(self, monkeypatch):
        """Test from_env raises ValueError when URL doesn't start with http/https"""
        monkeypatch.setenv("ATLASSIAN_URL", "ftp://test.atlassian.net")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="must start with http:// or https://"):
            AtlassianConfig.from_env()

    def test_from_dict_valid(self):
        """Test from_dict with valid dictionary"""
        data = {
            "url": "https://test.atlassian.net/",
            "username": "admin@example.com",
            "api_token": "token123456",
            "project_keys": ["PROJ1"],
            "enable_cache": False,
            "cache_dir": "/tmp/cache",
            "max_workers": 4,
        }

        config = AtlassianConfig.from_dict(data)

        assert config.url == "https://test.atlassian.net"
        assert config.username == "admin@example.com"
        assert config.api_token == "token123456"
        assert config.project_keys == ["PROJ1"]
        assert config.enable_cache is False
        assert config.cache_dir == "/tmp/cache"
        assert config.max_workers == 4

    def test_from_dict_missing_keys(self):
        """Test from_dict with missing keys defaults to empty strings"""
        config = AtlassianConfig.from_dict({})

        assert config.url == ""
        assert config.username == ""
        assert config.api_token == ""


class TestReportConfig:
    """Test ReportConfig class"""

    def test_create_report_config(self):
        """Test creating ReportConfig"""
        config = ReportConfig(year=2025)

        assert config.year == 2025
        assert config.include_tickets is True

    def test_default_report_config(self):
        """Test default ReportConfig"""
        config = ReportConfig.default(year=2025)

        assert config.year == 2025
        assert config.include_tickets is True


class TestExportConfig:
    """Test ExportConfig class"""

    def test_create_export_config(self):
        """Test creating ExportConfig"""
        config = ExportConfig(format="csv", filename="test.csv")

        assert config.format == "csv"
        assert config.filename == "test.csv"

    def test_get_filename_with_custom(self):
        """Test get_filename with custom filename"""
        config = ExportConfig(format="csv", filename="custom.csv")

        assert config.get_filename(2025) == "custom.csv"

    def test_get_filename_auto_csv(self):
        """Test get_filename auto-generation for CSV"""
        config = ExportConfig(format="csv")

        assert config.get_filename(2025) == "manhour_report_2025.csv"

    def test_get_filename_auto_excel(self):
        """Test get_filename auto-generation for Excel"""
        config = ExportConfig(format="excel")

        assert config.get_filename(2025) == "manhour_report_2025.xlsx"


class TestConfig:
    """Test main Config class"""

    def test_create_config(self):
        """Test creating Config"""
        atlassian_config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )

        config = Config(atlassian=atlassian_config)

        assert config.atlassian == atlassian_config
        assert config.report is not None
        assert config.export is not None

    def test_validate_config(self):
        """Test validating Config"""
        atlassian_config = AtlassianConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )

        config = Config(atlassian=atlassian_config)

        assert config.validate() is True
