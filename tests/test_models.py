"""
Tests for data models
"""

import pytest
from datetime import datetime

from src.models import (
    Author, Component, Worklog, Issue, WorkType,
    ProjectComponent, TimeEntry, MonthlyReport, YearlyReport
)


class TestAuthor:
    """Test Author model"""
    
    def test_create_author(self):
        """Test creating Author"""
        author = Author(
            email="test@example.com",
            display_name="Test User",
            account_id="123"
        )
        
        assert author.email == "test@example.com"
        assert author.display_name == "Test User"
        assert author.account_id == "123"
    
    def test_author_equality(self):
        """Test Author equality based on email and display_name (or account_id)"""
        # Same email and display_name
        author1 = Author(email="test@example.com", display_name="Test")
        author2 = Author(email="test@example.com", display_name="Test")
        assert author1 == author2
        
        # Same email, different display_name
        author3 = Author(email="test@example.com", display_name="Different")
        assert author1 != author3
        
        # Different email, same display_name
        author4 = Author(email="other@example.com", display_name="Test")
        assert author1 != author4
        
        # Same account_id (takes precedence)
        author5 = Author(email="test@example.com", display_name="Test", account_id="123")
        author6 = Author(email="different@example.com", display_name="Different", account_id="123")
        assert author5 == author6


class TestWorklog:
    """Test Worklog model"""
    
    def test_create_worklog(self):
        """Test creating Worklog"""
        author = Author(email="test@example.com", display_name="Test")
        worklog = Worklog(
            id="1",
            author=author,
            time_spent_seconds=3600,
            started=datetime(2025, 1, 15, 9, 0),
            issue_key="TEST-123"
        )
        
        assert worklog.id == "1"
        assert worklog.author == author
        assert worklog.time_spent_seconds == 3600
        assert worklog.issue_key == "TEST-123"
    
    def test_worklog_hours(self):
        """Test hours calculation"""
        author = Author(email="test@example.com", display_name="Test")
        worklog = Worklog(
            id="1",
            author=author,
            time_spent_seconds=7200,  # 2 hours
            started=datetime(2025, 1, 15, 9, 0),
            issue_key="TEST-123"
        )
        
        assert worklog.hours == 2.0
    

    
    def test_worklog_week_number(self):
        """Test week number calculation"""
        author = Author(email="test@example.com", display_name="Test")
        
        # Day 1-7 = Week 1
        worklog1 = Worklog(
            id="1", author=author, time_spent_seconds=3600,
            started=datetime(2025, 1, 5, 9, 0), issue_key="TEST-123"
        )
        assert worklog1.week_number == 1
        
        # Day 8-14 = Week 2
        worklog2 = Worklog(
            id="2", author=author, time_spent_seconds=3600,
            started=datetime(2025, 1, 10, 9, 0), issue_key="TEST-123"
        )
        assert worklog2.week_number == 2
        
        # Day 29+ = Week 5 (capped)
        worklog3 = Worklog(
            id="3", author=author, time_spent_seconds=3600,
            started=datetime(2025, 1, 30, 9, 0), issue_key="TEST-123"
        )
        assert worklog3.week_number == 5


class TestIssue:
    """Test Issue model"""
    
    def test_create_issue(self):
        """Test creating Issue"""
        component = Component(name="Backend")
        issue = Issue(
            key="TEST-123",
            summary="Test issue",
            issue_type="Task",
            components=[component],
            labels=["test"],
            work_type=WorkType.DEVELOPMENT,
            worklogs=[]
        )
        
        assert issue.key == "TEST-123"
        assert issue.summary == "Test issue"
        assert issue.work_type == WorkType.DEVELOPMENT
    
    def test_issue_total_hours(self):
        """Test total hours calculation"""
        author = Author(email="test@example.com", display_name="Test")
        worklog1 = Worklog(
            id="1", author=author, time_spent_seconds=3600,
            started=datetime(2025, 1, 15, 9, 0), issue_key="TEST-123"
        )
        worklog2 = Worklog(
            id="2", author=author, time_spent_seconds=7200,
            started=datetime(2025, 1, 16, 9, 0), issue_key="TEST-123"
        )
        
        issue = Issue(
            key="TEST-123",
            summary="Test",
            issue_type="Task",
            components=[Component(name="Backend")],
            labels=[],
            work_type=WorkType.DEVELOPMENT,
            worklogs=[worklog1, worklog2]
        )
        
        # 1 hour + 2 hours = 3 hours
        assert issue.get_total_hours() == 3.0


class TestProjectComponent:
    """Test ProjectComponent model"""
    
    def test_create_project_component(self):
        """Test creating ProjectComponent"""
        component = Component(name="Backend")
        pc = ProjectComponent(project="TEST", component=component)
        
        assert pc.project == "TEST"
        assert pc.component.name == "Backend"
    
    def test_project_component_equality(self):
        """Test ProjectComponent equality"""
        pc1 = ProjectComponent(project="TEST", component=Component(name="Backend"))
        pc2 = ProjectComponent(project="TEST", component=Component(name="Backend"))
        pc3 = ProjectComponent(project="OTHER", component=Component(name="Backend"))
        
        assert pc1 == pc2
        assert pc1 != pc3
    
    def test_project_component_str(self):
        """Test ProjectComponent string representation"""
        pc = ProjectComponent(project="TEST", component=Component(name="Backend"))
        
        assert str(pc) == "TEST - Backend"


class TestMonthlyReport:
    """Test MonthlyReport model"""
    
    def test_create_monthly_report(self):
        """Test creating MonthlyReport"""
        report = MonthlyReport(
            year=2025,
            month=1,
            project_keys=["TEST"],
            entries=[]
        )
        
        assert report.year == 2025
        assert report.month == 1
        assert report.month_name == "January"
    
    def test_monthly_report_total_hours(self):
        """Test total hours calculation"""
        author = Author(email="test@example.com", display_name="Test")
        pc = ProjectComponent(project="TEST", component=Component(name="Backend"))
        
        entry1 = TimeEntry(
            project_component=pc,
            author=author,
            hours=10.0,
            work_type=WorkType.DEVELOPMENT
        )
        entry2 = TimeEntry(
            project_component=pc,
            author=author,
            hours=5.0,
            work_type=WorkType.MAINTENANCE
        )
        
        report = MonthlyReport(
            year=2025,
            month=1,
            project_keys=["TEST"],
            entries=[entry1, entry2]
        )
        
        assert report.get_total_hours() == 15.0


class TestYearlyReport:
    """Test YearlyReport model"""
    
    def test_create_yearly_report(self):
        """Test creating YearlyReport"""
        report = YearlyReport(
            year=2025,
            project_keys=["TEST"],
            monthly_reports=[]
        )
        
        assert report.year == 2025
        assert report.project_keys == ["TEST"]
    
    def test_yearly_report_months_with_data(self):
        """Test counting months with data"""
        # Create monthly reports with and without data
        author = Author(email="test@example.com", display_name="Test")
        pc = ProjectComponent(project="TEST", component=Component(name="Backend"))
        
        entry = TimeEntry(
            project_component=pc,
            author=author,
            hours=10.0,
            work_type=WorkType.DEVELOPMENT
        )
        
        report1 = MonthlyReport(year=2025, month=1, project_keys=["TEST"], entries=[entry])
        report2 = MonthlyReport(year=2025, month=2, project_keys=["TEST"], entries=[])
        report3 = MonthlyReport(year=2025, month=3, project_keys=["TEST"], entries=[entry])
        
        yearly = YearlyReport(
            year=2025,
            project_keys=["TEST"],
            monthly_reports=[report1, report2, report3]
        )
        
        assert yearly.months_with_data == 2
