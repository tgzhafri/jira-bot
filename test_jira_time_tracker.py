#!/usr/bin/env python3
"""
Unit tests for Jira Time Tracker
"""

import pytest
import responses
from datetime import datetime
from unittest.mock import patch, MagicMock
from jira_time_tracker import JiraTimeTracker


class TestJiraTimeTracker:
    """Test cases for JiraTimeTracker class"""
    
    @pytest.fixture
    def tracker(self):
        """Create a JiraTimeTracker instance for testing"""
        return JiraTimeTracker(
            jira_url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test_token",
            filter_user="test@example.com"
        )
    
    @pytest.fixture
    def sample_issue_response(self):
        """Sample JIRA API response for testing"""
        return {
            "total": 1,
            "issues": [
                {
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue summary",
                        "components": [{"name": "Backend"}],
                        "labels": ["development"],
                        "issuetype": {"name": "Story"},
                        "customfield_10082": {"value": "Development"},
                        "worklog": {
                            "worklogs": [
                                {
                                    "author": {"emailAddress": "test@example.com"},
                                    "started": "2025-01-15T09:00:00.000+0000",
                                    "timeSpentSeconds": 7200,  # 2 hours
                                    "comment": "Working on feature"
                                }
                            ]
                        }
                    }
                }
            ]
        }
    
    def test_init(self, tracker):
        """Test JiraTimeTracker initialization"""
        assert tracker.jira_url == "https://test.atlassian.net"
        assert tracker.filter_user == "test@example.com"
        assert tracker.auth.username == "test@example.com"
        assert tracker.auth.password == "test_token"
    
    @responses.activate
    def test_make_request_success(self, tracker):
        """Test successful API request"""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/3/test",
            json={"result": "success"},
            status=200
        )
        
        result = tracker._make_request("test")
        assert result == {"result": "success"}
    
    @responses.activate
    def test_make_request_failure(self, tracker):
        """Test API request failure"""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/3/test",
            status=404
        )
        
        with pytest.raises(Exception):
            tracker._make_request("test")
    
    @responses.activate
    def test_get_issues_with_worklog_new_api(self, tracker, sample_issue_response):
        """Test get_issues_with_worklog uses new API endpoint"""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/3/search/jql",
            json=sample_issue_response,
            status=200
        )
        
        issues = tracker.get_issues_with_worklog("TEST", "2025-01-01", "2025-01-31")
        
        assert len(issues) == 1
        assert issues[0]["key"] == "TEST-123"
        
        # Verify the new endpoint was called
        assert len(responses.calls) == 1
        assert "search/jql" in responses.calls[0].request.url
    
    @responses.activate
    def test_get_issues_with_worklog_pagination(self, tracker):
        """Test pagination in get_issues_with_worklog"""
        # First page
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/3/search/jql",
            json={
                "total": 2,
                "issues": [{"key": "TEST-1"}]
            },
            status=200
        )
        
        # Second page
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/3/search/jql",
            json={
                "total": 2,
                "issues": [{"key": "TEST-2"}]
            },
            status=200
        )
        
        issues = tracker.get_issues_with_worklog("TEST", "2025-01-01", "2025-01-31")
        
        assert len(issues) == 2
        assert issues[0]["key"] == "TEST-1"
        assert issues[1]["key"] == "TEST-2"
        assert len(responses.calls) == 2
    
    def test_categorize_work_type_development(self, tracker):
        """Test work type categorization for development"""
        issue = {
            "fields": {
                "customfield_10082": {"value": "Development"},
                "issuetype": {"name": "Story"},
                "labels": []
            }
        }
        
        work_type = tracker.categorize_work_type(issue)
        assert work_type == "Development"
    
    def test_categorize_work_type_maintenance(self, tracker):
        """Test work type categorization for maintenance"""
        issue = {
            "fields": {
                "customfield_10082": {"value": "Maintenance"},
                "issuetype": {"name": "Bug"},
                "labels": ["bugfix"]
            }
        }
        
        work_type = tracker.categorize_work_type(issue)
        assert work_type == "Maintenance"
    
    def test_categorize_work_type_fallback_bug(self, tracker):
        """Test work type categorization fallback to bug type"""
        issue = {
            "fields": {
                "issuetype": {"name": "Bug"},
                "labels": []
            }
        }
        
        work_type = tracker.categorize_work_type(issue)
        assert work_type == "Maintenance"
    
    def test_categorize_work_type_fallback_default(self, tracker):
        """Test work type categorization fallback to default"""
        issue = {
            "fields": {
                "issuetype": {"name": "Story"},
                "labels": []
            }
        }
        
        work_type = tracker.categorize_work_type(issue)
        assert work_type == "Development"
    
    def test_get_week_number(self, tracker):
        """Test week number calculation"""
        # Test different dates in January 2025
        assert tracker.get_week_number("2025-01-01T09:00:00.000+0000") == 1  # Day 1
        assert tracker.get_week_number("2025-01-07T09:00:00.000+0000") == 1  # Day 7
        assert tracker.get_week_number("2025-01-08T09:00:00.000+0000") == 2  # Day 8
        assert tracker.get_week_number("2025-01-15T09:00:00.000+0000") == 3  # Day 15
        assert tracker.get_week_number("2025-01-31T09:00:00.000+0000") == 5  # Day 31 (capped at 5)
    
    def test_process_worklog_data(self, tracker):
        """Test worklog data processing"""
        issues = [
            {
                "key": "TEST-123",
                "fields": {
                    "summary": "Test issue",
                    "components": [{"name": "Backend"}],
                    "customfield_10082": {"value": "Development"},
                    "issuetype": {"name": "Story"},
                    "labels": [],
                    "worklog": {
                        "worklogs": [
                            {
                                "author": {"emailAddress": "test@example.com"},
                                "started": "2025-01-15T09:00:00.000+0000",
                                "timeSpentSeconds": 7200  # 2 hours
                            }
                        ]
                    }
                }
            }
        ]
        
        data = tracker.process_worklog_data(issues, "2025-01-01", "2025-01-31")
        
        # Check structure
        assert "Backend" in data
        assert "Development" in data["Backend"]
        assert "total" in data["Backend"]["Development"]
        assert "W3" in data["Backend"]["Development"]["total"]
        
        # Check hours (2 hours * 1.3 factor = 2.6 hours)
        assert data["Backend"]["Development"]["total"]["W3"] == 2.6
        
        # Check ticket details
        assert "_ticket_details" in data
        ticket_details = data["_ticket_details"]
        assert len(ticket_details) == 1
        
        ticket_key = list(ticket_details.keys())[0]
        ticket_info = ticket_details[ticket_key]
        assert ticket_info["key"] == "TEST-123"
        assert ticket_info["total_hours"] == 2.6
        assert ticket_info["weeks"]["W3"] == 2.6
    
    def test_process_worklog_data_filter_user(self, tracker):
        """Test worklog data processing filters by user"""
        issues = [
            {
                "key": "TEST-123",
                "fields": {
                    "summary": "Test issue",
                    "components": [{"name": "Backend"}],
                    "customfield_10082": {"value": "Development"},
                    "issuetype": {"name": "Story"},
                    "labels": [],
                    "worklog": {
                        "worklogs": [
                            {
                                "author": {"emailAddress": "other@example.com"},  # Different user
                                "started": "2025-01-15T09:00:00.000+0000",
                                "timeSpentSeconds": 7200
                            }
                        ]
                    }
                }
            }
        ]
        
        data = tracker.process_worklog_data(issues, "2025-01-01", "2025-01-31")
        
        # Should have no data since worklog is from different user
        assert len(data) == 1  # Only _ticket_details
        assert "_ticket_details" in data
        assert len(data["_ticket_details"]) == 0
    
    def test_process_worklog_data_date_filter(self, tracker):
        """Test worklog data processing filters by date range"""
        issues = [
            {
                "key": "TEST-123",
                "fields": {
                    "summary": "Test issue",
                    "components": [{"name": "Backend"}],
                    "customfield_10082": {"value": "Development"},
                    "issuetype": {"name": "Story"},
                    "labels": [],
                    "worklog": {
                        "worklogs": [
                            {
                                "author": {"emailAddress": "test@example.com"},
                                "started": "2024-12-15T09:00:00.000+0000",  # Outside date range
                                "timeSpentSeconds": 7200
                            }
                        ]
                    }
                }
            }
        ]
        
        data = tracker.process_worklog_data(issues, "2025-01-01", "2025-01-31")
        
        # Should have no data since worklog is outside date range
        assert len(data) == 1  # Only _ticket_details
        assert "_ticket_details" in data
        assert len(data["_ticket_details"]) == 0
    
    @responses.activate
    def test_generate_monthly_report(self, tracker, sample_issue_response):
        """Test monthly report generation"""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/rest/api/3/search/jql",
            json=sample_issue_response,
            status=200
        )
        
        report = tracker.generate_monthly_report("TEST", 2025, 1)
        
        assert "Backend" in report
        assert "_ticket_details" in report
    
    @patch('builtins.print')
    @responses.activate
    def test_generate_yearly_report(self, mock_print, tracker, sample_issue_response):
        """Test yearly report generation"""
        # Mock the API response for all months
        for _ in range(12):
            responses.add(
                responses.GET,
                "https://test.atlassian.net/rest/api/3/search/jql",
                json=sample_issue_response,
                status=200
            )
        
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            tracker.generate_yearly_report(["TEST"], 2025)
            
            # Verify file was created
            mock_open.assert_called_with("manhour_report_2025.txt", 'w', encoding='utf-8')
            mock_file.write.assert_called()
    
    def test_get_monthly_report_text_no_data(self, tracker):
        """Test monthly report text generation with no data"""
        lines = tracker.get_monthly_report_text("TEST", 2025, 1, {})
        
        assert any("No worklog data found" in line for line in lines)
    
    def test_get_monthly_report_text_with_data(self, tracker):
        """Test monthly report text generation with data"""
        worklog_data = {
            "Backend": {
                "Development": {
                    "total": {"W1": 8.0, "W2": 4.0}
                }
            },
            "_ticket_details": {
                "Backend|Development|TEST-123": {
                    "key": "TEST-123",
                    "summary": "Test issue",
                    "component": "Backend",
                    "work_type": "Development",
                    "total_hours": 12.0,
                    "weeks": {"W1": 8.0, "W2": 4.0}
                }
            }
        }
        
        lines = tracker.get_monthly_report_text("TEST", 2025, 1, worklog_data)
        
        # Check that report contains expected elements
        assert any("January 2025" in line for line in lines)
        assert any("Backend" in line for line in lines)
        assert any("TEST-123" in line for line in lines)
        assert any("12.0" in line for line in lines)  # Total hours


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing main function"""
    return {
        'JIRA_URL': 'https://test.atlassian.net',
        'JIRA_USERNAME': 'test@example.com',
        'JIRA_API_TOKEN': 'test_token',
        'JIRA_PROJECT_KEY': 'TEST,DEMO'
    }


class TestMainFunction:
    """Test cases for main function"""
    
    @patch('jira_time_tracker.load_dotenv')  # Mock dotenv loading
    @patch.dict('os.environ', {}, clear=True)  # Clear all env vars
    @patch('builtins.print')
    def test_main_missing_env_vars(self, mock_print, mock_load_dotenv):
        """Test main function with missing environment variables"""
        from jira_time_tracker import main
        
        main()
        
        # Check that error message was printed
        mock_print.assert_called()
        calls = [str(call.args[0]) if call.args else str(call) for call in mock_print.call_args_list]
        assert any("Missing environment variables" in call for call in calls)
    
    @patch('jira_time_tracker.JiraTimeTracker')
    @patch('builtins.print')
    def test_main_success(self, mock_print, mock_tracker_class, mock_env_vars):
        """Test successful main function execution"""
        with patch.dict('os.environ', mock_env_vars):
            mock_tracker = MagicMock()
            mock_tracker_class.return_value = mock_tracker
            
            from jira_time_tracker import main
            main()
            
            # Verify tracker was created and yearly report was called
            mock_tracker_class.assert_called_once()
            mock_tracker.generate_yearly_report.assert_called_once()
    
    @patch('jira_time_tracker.JiraTimeTracker')
    @patch('builtins.print')
    def test_main_exception_handling(self, mock_print, mock_tracker_class, mock_env_vars):
        """Test main function exception handling"""
        with patch.dict('os.environ', mock_env_vars):
            mock_tracker = MagicMock()
            mock_tracker.generate_yearly_report.side_effect = Exception("Test error")
            mock_tracker_class.return_value = mock_tracker
            
            from jira_time_tracker import main
            main()
            
            # Check that error was printed
            calls = [str(call.args[0]) if call.args else str(call) for call in mock_print.call_args_list]
            assert any("Error: Test error" in call for call in calls)


if __name__ == "__main__":
    pytest.main([__file__])