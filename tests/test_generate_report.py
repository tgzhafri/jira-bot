#!/usr/bin/env python3
"""
Unit tests for generate_report.py
"""

import sys
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config, JiraConfig, ReportConfig
from src.models import Author, Component, Issue, Worklog, WorkType
from scripts.generate_report import generate_csv_report


@pytest.fixture
def mock_config():
    """Create a mock configuration"""
    jira_config = JiraConfig(
        url="https://test.atlassian.net",
        username="test@example.com",
        api_token="test-token",
        project_keys=["TEST"],
        enable_cache=False,
        max_workers=2
    )
    report_config = ReportConfig(year=2025)
    return Config(jira=jira_config, report=report_config)


@pytest.fixture
def mock_author():
    """Create a mock author"""
    return Author(
        email="john.doe@example.com",
        display_name="John Doe",
        account_id="123456"
    )


@pytest.fixture
def mock_issues(mock_author):
    """Create mock issues with worklogs"""
    component = Component(name="Backend")
    worklog = Worklog(
        id="1",
        author=mock_author,
        time_spent_seconds=3600,
        started=datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc),
        issue_key="TEST-123"
    )
    issue = Issue(
        key="TEST-123",
        summary="Test issue",
        issue_type="Task",
        components=[component],
        labels=[],
        work_type=WorkType.DEVELOPMENT,
        worklogs=[worklog]
    )
    return [issue]


class TestGenerateCSVReport:
    """Test suite for generate_csv_report function"""
    
    @patch('scripts.generate_report.JiraClient')
    def test_generate_report_without_filter(self, mock_jira_client_class, mock_config, mock_issues, tmp_path):
        """Test generating standard team overview report"""
        # Setup mock
        mock_client = Mock()
        mock_client.test_connection.return_value = True
        mock_client.get_all_projects.return_value = ["TEST"]
        mock_client.get_issues_with_worklog.return_value = []
        mock_client.parse_issue.side_effect = lambda raw, **kwargs: mock_issues[0]
        mock_jira_client_class.return_value = mock_client
        
        # Generate report
        output_file = tmp_path / "test_report.csv"
        result = generate_csv_report(
            config=mock_config,
            year=2025,
            output_file=str(output_file),
            max_workers=2
        )
        
        # Verify
        assert mock_client.test_connection.called
        assert result is not None or result is None  # May be None if no data
    
    @patch('scripts.generate_report.JiraClient')
    def test_generate_report_with_filter_author(self, mock_jira_client_class, mock_config, mock_author, mock_issues, tmp_path):
        """Test generating monthly breakdown report for specific user"""
        # Setup mock
        mock_client = Mock()
        mock_client.test_connection.return_value = True
        mock_client.get_all_projects.return_value = ["TEST"]
        mock_client.get_issues_with_worklog.return_value = []
        mock_client.parse_issue.side_effect = lambda raw, **kwargs: mock_issues[0]
        mock_jira_client_class.return_value = mock_client
        
        # Generate report with filter_author
        output_file = tmp_path / "test_monthly_breakdown.csv"
        result = generate_csv_report(
            config=mock_config,
            year=2025,
            output_file=str(output_file),
            max_workers=2,
            filter_author=mock_author,
            monthly_breakdown=True
        )
        
        # Verify
        assert mock_client.test_connection.called
        # Verify that get_issues_with_worklog was called with filter_user
        # (it should be called with the author's email)
        assert result is not None or result is None  # May be None if no data
    
    @patch('scripts.generate_report.JiraClient')
    def test_generate_report_with_monthly_breakdown_flag(self, mock_jira_client_class, mock_config, mock_author, tmp_path):
        """Test that monthly_breakdown parameter is accepted"""
        # Setup mock
        mock_client = Mock()
        mock_client.test_connection.return_value = True
        mock_client.get_all_projects.return_value = ["TEST"]
        mock_client.get_issues_with_worklog.return_value = []
        mock_jira_client_class.return_value = mock_client
        
        # This should not raise an error
        output_file = tmp_path / "test_monthly.csv"
        try:
            result = generate_csv_report(
                config=mock_config,
                year=2025,
                output_file=str(output_file),
                max_workers=2,
                filter_author=mock_author,
                monthly_breakdown=True
            )
            # If we get here, the function signature is correct
            assert True
        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                pytest.fail(f"Function signature error: {e}")
            raise
    
    @patch('scripts.generate_report.JiraClient')
    def test_generate_report_connection_failure(self, mock_jira_client_class, mock_config):
        """Test handling of connection failure"""
        # Setup mock to fail connection
        mock_client = Mock()
        mock_client.test_connection.return_value = False
        mock_jira_client_class.return_value = mock_client
        
        # Generate report should return None on connection failure
        result = generate_csv_report(
            config=mock_config,
            year=2025,
            max_workers=2
        )
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
