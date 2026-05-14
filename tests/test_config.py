"""
Tests for configuration module
"""

import pytest
import os
from pathlib import Path

from src.config import JiraConfig, ReportConfig, ExportConfig, Config, AtlassianConfig, ConfluenceConfig


class TestJiraConfig:
    """Test JiraConfig class"""
    
    def test_create_jira_config(self):
        """Test creating JiraConfig"""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )
        
        assert config.url == "https://test.atlassian.net"
        assert config.username == "test@example.com"
        assert config.api_token == "test-token"
        assert config.project_keys == ["TEST"]
    
    def test_validate_valid_config(self):
        """Test validation with valid config"""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="valid-token-123",
            project_keys=["TEST"]
        )
        
        assert config.validate() is True
    
    def test_validate_invalid_url(self):
        """Test validation with invalid URL"""
        config = JiraConfig(
            url="invalid-url",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )
        
        with pytest.raises(ValueError, match="Invalid ATLASSIAN_URL"):
            config.validate()
    
    def test_validate_invalid_username(self):
        """Test validation with invalid username"""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="invalid",
            api_token="test-token",
            project_keys=["TEST"]
        )
        
        with pytest.raises(ValueError, match="Invalid ATLASSIAN_USERNAME"):
            config.validate()
    
    def test_validate_no_project_keys(self):
        """Test validation with no project keys (should be valid - will fetch all)"""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token-123456",
            project_keys=None  # None means fetch all projects
        )
        
        # Should not raise - None is valid (means fetch all)
        assert config.validate() is True

    def test_from_env_falls_back_to_legacy_jira_vars(self, monkeypatch):
        """Test from_env falls back to JIRA_* env vars when ATLASSIAN_* are missing"""
        monkeypatch.delenv("ATLASSIAN_URL", raising=False)
        monkeypatch.delenv("ATLASSIAN_USERNAME", raising=False)
        monkeypatch.delenv("ATLASSIAN_API_TOKEN", raising=False)
        monkeypatch.setenv("JIRA_URL", "https://legacy.atlassian.net/")
        monkeypatch.setenv("JIRA_USERNAME", "legacy@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "legacy-token-123")

        config = JiraConfig.from_env()

        assert config.url == "https://legacy.atlassian.net"
        assert config.username == "legacy@example.com"
        assert config.api_token == "legacy-token-123"

    def test_from_env_prefers_atlassian_over_jira_vars(self, monkeypatch):
        """Test from_env prefers ATLASSIAN_* over JIRA_* when both are set"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://new.atlassian.net")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "new@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "new-token-12345")
        monkeypatch.setenv("JIRA_URL", "https://old.atlassian.net")
        monkeypatch.setenv("JIRA_USERNAME", "old@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "old-token-12345")

        config = JiraConfig.from_env()

        assert config.url == "https://new.atlassian.net"
        assert config.username == "new@example.com"
        assert config.api_token == "new-token-12345"


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
        jira_config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )
        
        config = Config(jira=jira_config)
        
        assert config.jira == jira_config
        assert config.atlassian is not None
        assert config.atlassian.url == jira_config.url
        assert config.report is not None
        assert config.export is not None
    
    def test_validate_config(self):
        """Test validating Config"""
        jira_config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            project_keys=["TEST"]
        )
        
        config = Config(jira=jira_config)
        
        assert config.validate() is True


class TestAtlassianConfig:
    """Test AtlassianConfig class (also aliased as ConfluenceConfig)"""

    def test_confluence_config_alias(self):
        """Test that ConfluenceConfig is an alias for AtlassianConfig"""
        assert ConfluenceConfig is AtlassianConfig

    def test_create_atlassian_config(self):
        """Test creating AtlassianConfig directly"""
        config = AtlassianConfig(
            url="https://confluence.example.com",
            username="admin@example.com",
            api_token="secret-token-long-enough",
        )
        assert config.url == "https://confluence.example.com"
        assert config.username == "admin@example.com"
        assert config.api_token == "secret-token-long-enough"

    def test_from_env_valid(self, monkeypatch):
        """Test from_env with valid environment variables"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://confluence.example.com/")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        config = ConfluenceConfig.from_env()

        assert config.url == "https://confluence.example.com"
        assert config.username == "admin@example.com"
        assert config.api_token == "token123456"

    def test_from_env_strips_trailing_slashes(self, monkeypatch):
        """Test that from_env normalizes URL by stripping trailing slashes"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://confluence.example.com///")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        config = ConfluenceConfig.from_env()

        assert config.url == "https://confluence.example.com"

    def test_from_env_strips_whitespace(self, monkeypatch):
        """Test that from_env strips leading/trailing whitespace from values"""
        monkeypatch.setenv("ATLASSIAN_URL", "  https://confluence.example.com  ")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "  admin@example.com  ")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "  token123456  ")

        config = ConfluenceConfig.from_env()

        assert config.url == "https://confluence.example.com"
        assert config.username == "admin@example.com"
        assert config.api_token == "token123456"

    def test_from_env_missing_url(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_URL is missing"""
        monkeypatch.delenv("ATLASSIAN_URL", raising=False)
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_URL"):
            ConfluenceConfig.from_env()

    def test_from_env_empty_url(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_URL is empty"""
        monkeypatch.setenv("ATLASSIAN_URL", "")
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_URL"):
            ConfluenceConfig.from_env()

    def test_from_env_whitespace_only_url(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_URL is whitespace only"""
        monkeypatch.setenv("ATLASSIAN_URL", "   ")
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_URL"):
            ConfluenceConfig.from_env()

    def test_from_env_missing_username(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_USERNAME is missing"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://confluence.example.com")
        monkeypatch.delenv("ATLASSIAN_USERNAME", raising=False)
        monkeypatch.delenv("JIRA_USERNAME", raising=False)
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="ATLASSIAN_USERNAME"):
            ConfluenceConfig.from_env()

    def test_from_env_missing_api_token(self, monkeypatch):
        """Test from_env raises ValueError when ATLASSIAN_API_TOKEN is missing"""
        monkeypatch.setenv("ATLASSIAN_URL", "https://confluence.example.com")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.delenv("ATLASSIAN_API_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

        with pytest.raises(ValueError, match="ATLASSIAN_API_TOKEN"):
            ConfluenceConfig.from_env()

    def test_from_env_invalid_url_scheme(self, monkeypatch):
        """Test from_env raises ValueError when URL doesn't start with http/https"""
        monkeypatch.setenv("ATLASSIAN_URL", "ftp://confluence.example.com")
        monkeypatch.setenv("ATLASSIAN_USERNAME", "admin@example.com")
        monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token123456")

        with pytest.raises(ValueError, match="must start with http:// or https://"):
            ConfluenceConfig.from_env()

    def test_from_env_falls_back_to_legacy_jira_vars(self, monkeypatch):
        """Test from_env falls back to JIRA_* env vars when ATLASSIAN_* are missing"""
        monkeypatch.delenv("ATLASSIAN_URL", raising=False)
        monkeypatch.delenv("ATLASSIAN_USERNAME", raising=False)
        monkeypatch.delenv("ATLASSIAN_API_TOKEN", raising=False)
        monkeypatch.setenv("JIRA_URL", "https://legacy.example.com/")
        monkeypatch.setenv("JIRA_USERNAME", "legacy@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "legacy-token-123")

        config = ConfluenceConfig.from_env()

        assert config.url == "https://legacy.example.com"
        assert config.username == "legacy@example.com"
        assert config.api_token == "legacy-token-123"

    def test_from_dict_valid(self):
        """Test from_dict with valid dictionary"""
        data = {
            "url": "https://confluence.example.com/",
            "username": "admin@example.com",
            "api_token": "token123456",
        }

        config = ConfluenceConfig.from_dict(data)

        assert config.url == "https://confluence.example.com"
        assert config.username == "admin@example.com"
        assert config.api_token == "token123456"

    def test_from_dict_missing_keys(self):
        """Test from_dict with missing keys defaults to empty strings"""
        config = ConfluenceConfig.from_dict({})

        assert config.url == ""
        assert config.username == ""
        assert config.api_token == ""

    def test_validate_valid_config(self):
        """Test validate with valid configuration"""
        config = ConfluenceConfig(
            url="https://confluence.example.com",
            username="admin@example.com",
            api_token="token123456",
        )

        assert config.validate() is True

    def test_validate_invalid_url_scheme(self):
        """Test validate raises ValueError for invalid URL scheme"""
        config = ConfluenceConfig(
            url="ftp://confluence.example.com",
            username="admin@example.com",
            api_token="token123456",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_URL"):
            config.validate()

    def test_validate_empty_url(self):
        """Test validate raises ValueError for empty URL"""
        config = ConfluenceConfig(url="", username="admin@example.com", api_token="token123456")

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_URL"):
            config.validate()

    def test_validate_empty_username(self):
        """Test validate raises ValueError for empty username"""
        config = ConfluenceConfig(
            url="https://confluence.example.com",
            username="",
            api_token="token123456",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_USERNAME"):
            config.validate()

    def test_validate_username_without_at(self):
        """Test validate raises ValueError for username without @ symbol"""
        config = ConfluenceConfig(
            url="https://confluence.example.com",
            username="admin",
            api_token="token123456",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_USERNAME"):
            config.validate()

    def test_validate_empty_api_token(self):
        """Test validate raises ValueError for empty api_token"""
        config = ConfluenceConfig(
            url="https://confluence.example.com",
            username="admin@example.com",
            api_token="",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_API_TOKEN"):
            config.validate()

    def test_validate_short_api_token(self):
        """Test validate raises ValueError for api_token shorter than 10 chars"""
        config = ConfluenceConfig(
            url="https://confluence.example.com",
            username="admin@example.com",
            api_token="short",
        )

        with pytest.raises(ValueError, match="Invalid ATLASSIAN_API_TOKEN"):
            config.validate()
