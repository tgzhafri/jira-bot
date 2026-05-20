"""Integration tests for Automate Jira."""

from datetime import datetime, timezone
from pathlib import Path

def test_imports():
    """Test all imports work"""
    from src.config import Config, AtlassianConfig, ReportConfig, ExportConfig
    from src.models import (
        Issue, Worklog, Author, Component, WorkType,
        ProjectComponent, TimeEntry, MonthlyReport, YearlyReport
    )
    from src.services.jira_client import JiraClient, JiraClientError
    from src.processors import WorklogProcessor
    from src.exporters import YearlyOverviewExporter, BaseExporter
    from src.utils import get_month_range, format_date_for_jql, setup_logging

def test_date_utils():
    """Test date utilities"""
    from src.utils import get_month_range, format_date_for_jql

    # Test get_month_range
    start, end = get_month_range(2025, 1)
    assert start.tzinfo is not None, "start_date should be timezone-aware"
    assert end.tzinfo is not None, "end_date should be timezone-aware"
    assert start.year == 2025
    assert start.month == 1
    assert start.day == 1
    assert end.month == 1
    assert end.day == 31

    # Test format_date_for_jql
    dt = datetime(2025, 1, 15, tzinfo=timezone.utc)
    formatted = format_date_for_jql(dt)
    assert formatted == "2025-01-15"

def test_models():
    """Test data models"""
    from src.models import Author, Component, Worklog, Issue, WorkType

    # Test Author
    author = Author(email="test@example.com", display_name="Test User")
    assert author.email == "test@example.com"

    # Test Component
    component = Component(name="Backend")
    assert component.name == "Backend"

    # Test Worklog
    worklog = Worklog(
        id="1",
        author=author,
        time_spent_seconds=3600,
        started=datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc),
        issue_key="TEST-123"
    )
    assert worklog.hours == 1.0

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

def test_config():
    """Test configuration"""
    from src.config import AtlassianConfig, ReportConfig, Config

    # Test AtlassianConfig
    atlassian_config = AtlassianConfig(
        url="https://test.atlassian.net",
        username="test@example.com",
        api_token="test-token-123456",
        project_keys=["TEST"]
    )
    assert atlassian_config.validate()

    # Test ReportConfig
    report_config = ReportConfig(year=2025)
    assert report_config.year == 2025

    # Test Config
    config = Config(atlassian=atlassian_config, report=report_config)
    assert config.validate()

def test_processor():
    """Test worklog processor"""
    from src.processors import WorklogProcessor
    from src.config import ReportConfig
    from src.models import Issue, Worklog, Author, Component, WorkType

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

def test_csv_exporter():
    """Test CSV exporter"""
    from src.exporters import YearlyOverviewExporter
    from src.models import (
        YearlyReport, MonthlyReport, TimeEntry,
        ProjectComponent, Component, Author, WorkType
    )

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

def test_jira_client_parsing():
    """Test Jira client parsing logic"""
    from src.services.jira_client import JiraClient
    from src.config import AtlassianConfig

    config = AtlassianConfig(
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

    # Test field value extraction
    value = client._extract_field_value({'value': 'test'})
    assert value == 'test'
    value = client._extract_field_value('test')
    assert value == 'test'


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
        try:
            test_func()
            results.append((name, True))
        except Exception as e:
            print(f"  ❌ {name} failed: {e}")
            results.append((name, False))

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
