
import unittest
from datetime import datetime
from src.models import Issue, Component, Worklog, Author, WorkType
from src.processors.worklog_processor import WorklogProcessor
from src.config import ReportConfig

class TestWorklogDistribution(unittest.TestCase):
    def test_worklog_distribution_multiple_components(self):
        # Create dummy components
        comp_a = Component(name="Component A")
        comp_b = Component(name="Component B")
        
        # Create dummy author
        author = Author(email="test@example.com", display_name="Test User")
        
        # Create dummy worklog (10 hours)
        worklog = Worklog(
            id="1001",
            author=author,
            time_spent_seconds=36000, # 10 hours
            started=datetime(2023, 1, 1, 10, 0),
            issue_key="TEST-1"
        )
        
        # Create dummy issue with 2 components
        issue = Issue(
            key="TEST-1",
            summary="Test Issue",
            issue_type="Task",
            components=[comp_a, comp_b],
            labels=[],
            work_type=WorkType.DEVELOPMENT,
            worklogs=[worklog]
        )
        
        # Initialize processor
        config = ReportConfig(year=2023)
        processor = WorklogProcessor(config)
        
        # Process issues
        entries = processor.process_issues(
            issues=[issue],
            project_key="TEST",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 31)
        )
        
        # Check results
        # We expect 2 entries (one for each component)
        self.assertEqual(len(entries), 2)
        
        total_hours = sum(entry.hours for entry in entries)
        
        # CURRENT BEHAVIOR: 10 hours per component = 20 hours total
        # DESIRED BEHAVIOR: 5 hours per component = 10 hours total
        
        print(f"Total aggregated hours: {total_hours}")
        for entry in entries:
            print(f"Component: {entry.project_component.component.name}, Hours: {entry.hours}")
            
        # This assertion expects the DESIRED behavior, so it should FAIL currently
        self.assertEqual(total_hours, 10.0, f"Expected 10.0 total hours, but got {total_hours}")
        
        for entry in entries:
            self.assertEqual(entry.hours, 5.0, f"Expected 5.0 hours for component {entry.project_component.component.name}, but got {entry.hours}")

if __name__ == '__main__':
    unittest.main()
