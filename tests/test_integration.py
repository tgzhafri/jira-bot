#!/usr/bin/env python3
"""
Integration test for Automate Jira
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test all imports work"""
    print("Testing imports...")
    try:
        from src.config import Config, JiraConfig, ReportConfig, ExportConfig
        from src.models import (
            Issue, Worklog, Author, Component, WorkType,
            ProjectComponent, TimeEntry, MonthlyReport, YearlyReport
        )
        from src.jira_client import JiraClient, JiraClientError
        from src.processors import WorklogProcessor
        from src.exporters import CSVExporter, BaseExporter
        from src.utils import get_month_range, format_date_for_jql, setup_logging
        print("  ✅ All imports successful")
        return True
    except ImportError as e:
        print(f"  ❌ Import failed: {e}")
        return False

def test_date_utils():
    """Test date utilities"""
    print("\nTesting date utilities...")
    from src.utils import get_month_range, format_date_for_jql
    
    try:
        # Test get_month_range
        start, end = get_month_range(2025, 1)
        assert start.tzinfo is not None, "start_date should be timezone-aware"
        assert end.tzinfo is not None, "end_date should be timezone-aware"
        assert start.year == 2025
        assert start.month == 1
        assert start.day == 1
        assert end.month == 1
        assert end.day == 31
        print("  ✅ get_month_range works correctly")
        
        # Test format_date_for_jql
        dt = datetime(2025, 1, 15, tzinfo=timezone.utc)
        formatted = format_date_for_jql(dt)
        assert formatted == "2025-01-15"
        print("  ✅ format_date_for_jql works correctly")
        
        return True
    except Exception as e:
        print(f"  ❌ Date utils test failed: {e}")
        return False

def test_models():
    """Test data models"""
    print("\nTesting data models...")
    from src.models import Author, Component, Worklog, Issue, WorkType
    
    try:
        # Test Author
        author = Author(email="test@example.com", display_name="Test User")
        assert author.email == "test@example.com"
        print("  ✅ Author model works")
        
        # Test Component
        component = Component(name="Backend")
        assert component.name == "Backend"
        print("  ✅ Component model works")
        
        # Test Worklog
        worklog = Worklog(
            id="1",
            author=author,
            time_spent_seconds=3600,
            started=datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc),
            issue_key="TEST-123"
        )
        assert worklog.hours == 1.0
        print("  ✅ Worklog model works")
        
        # Test Issue
        issue = Issue(
            key="TEST-123",
            summary="Test issue",
            issue_type="Task",
            components=[component],
            labels=["test"],
            work_type=WorkType.DEVELOPMENT,
            worklogs=[worklog]
        )
        assert issue.get_total_hours() == 1.0
        print("  ✅ Issue model works")
        
        return True
    except Exception as e:
        print(f"  ❌ Models test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config():
    """Test configuration"""
    print("\nTesting configuration...")
    from src.config import JiraConfig, ReportConfig, Config
    
    try:
        # Test JiraConfig
        jira_config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token-123456",
            project_keys=["TEST"]
        )
        assert jira_config.validate()
        print("  ✅ JiraConfig works")
        
        # Test ReportConfig
        report_config = ReportConfig(year=2025)
        assert report_config.year == 2025
        print("  ✅ ReportConfig works")
        
        # Test Config
        config = Config(jira=jira_config, report=report_config)
        assert config.validate()
        print("  ✅ Config works")
        
        return True
    except Exception as e:
        print(f"  ❌ Config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_processor():
    """Test worklog processor"""
    print("\nTesting worklog processor...")
    from src.processors import WorklogProcessor
    from src.config import ReportConfig
    from src.models import Issue, Worklog, Author, Component, WorkType
    
    try:
        config = ReportConfig(year=2025)
        processor = WorklogProcessor(config)
        
        # Create test data
        author = Author(email="test@example.com", display_name="Test User")
        component = Component(name="Backend")
        worklog = Worklog(
            id="1",
            author=author,
            time_spent_seconds=3600,
            started=datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc),
            issue_key="TEST-123"
        )
        issue = Issue(
            key="TEST-123",
            summary="Test",
            issue_type="Task",
            components=[component],
            labels=[],
            work_type=WorkType.DEVELOPMENT,
            worklogs=[worklog]
        )
        
        # Process issues
        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
        entries = processor.process_issues([issue], "TEST", start_date, end_date)
        
        assert len(entries) > 0
        assert entries[0].hours == 1.0
        print("  ✅ WorklogProcessor works")
        
        return True
    except Exception as e:
        print(f"  ❌ Processor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_csv_exporter():
    """Test CSV exporter"""
    print("\nTesting CSV exporter...")
    from src.exporters import YearlyOverviewExporter
    from src.models import (
        YearlyReport, MonthlyReport, TimeEntry, 
        ProjectComponent, Component, Author, WorkType
    )
    
    try:
        # Create test data
        author = Author(email="test@example.com", display_name="Test User")
        pc = ProjectComponent(project="TEST", component=Component(name="Backend"))
        entry = TimeEntry(
            project_component=pc,
            author=author,
            hours=10.0,
            work_type=WorkType.DEVELOPMENT
        )
        
        monthly = MonthlyReport(
            year=2025,
            month=1,
            project_keys=["TEST"],
            entries=[entry]
        )
        
        yearly = YearlyReport(
            year=2025,
            project_keys=["TEST"],
            monthly_reports=[monthly]
        )
        
        # Export
        output_path = Path("test_report.csv")
        exporter = YearlyOverviewExporter(output_path)
        result = exporter.export_yearly(yearly)
        
        assert result.exists()
        
        # Read and verify
        with open(result, 'r') as f:
            content = f.read()
            assert "Project,Component" in content
            assert "Test User" in content
            assert "10.0" in content
        
        # Cleanup
        output_path.unlink()
        
        print("  ✅ YearlyOverviewExporter works")
        return True
    except Exception as e:
        print(f"  ❌ CSV exporter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_jira_client_parsing():
    """Test Jira client parsing logic"""
    print("\nTesting Jira client parsing...")
    from src.jira_client import JiraClient
    from src.config import JiraConfig
    
    try:
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token-123456",
            project_keys=["TEST"]
        )
        client = JiraClient(config)
        
        # Test work type categorization
        fields = {
            'customfield_10082': {'value': 'Development'},
            'issuetype': {'name': 'Task'},
            'labels': []
        }
        work_type = client._categorize_work_type(fields)
        assert work_type.value == "Development"
        print("  ✅ Work type categorization works")
        
        # Test field value extraction
        value = client._extract_field_value({'value': 'test'})
        assert value == 'test'
        value = client._extract_field_value('test')
        assert value == 'test'
        print("  ✅ Field value extraction works")
        
        return True
    except Exception as e:
        print(f"  ❌ Jira client test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("="*60)
    print("  Automate Jira - Integration Tests")
    print("="*60)
    
    tests = [
        ("Imports", test_imports),
        ("Date Utils", test_date_utils),
        ("Models", test_models),
        ("Configuration", test_config),
        ("Processor", test_processor),
        ("CSV Exporter", test_csv_exporter),
        ("Jira Client", test_jira_client_parsing),
    ]
    
    results = []
    for name, test_func in tests:
        result = test_func()
        results.append((name, result))
    
    print("\n" + "="*60)
    print("  Test Results")
    print("="*60)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
        if not result:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\n✨ All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
