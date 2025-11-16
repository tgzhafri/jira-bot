"""
Tests for configuration module
"""

import pytest
import os
from pathlib import Path

from src.config import JiraConfig, ReportConfig, ExportConfig, Config


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
        
        with pytest.raises(ValueError, match="Invalid JIRA_URL"):
            config.validate()
    
    def test_validate_invalid_username(self):
        """Test validation with invalid username"""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="invalid",
            api_token="test-token",
            project_keys=["TEST"]
        )
        
        with pytest.raises(ValueError, match="Invalid JIRA_USERNAME"):
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
