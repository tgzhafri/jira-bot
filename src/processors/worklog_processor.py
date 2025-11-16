"""
Worklog data processing and aggregation
"""

import logging
from typing import List, Dict
from datetime import datetime, timedelta
from collections import defaultdict

from ..models import (
    Issue, TimeEntry, ProjectComponent, MonthlyReport,
    YearlyReport, Author, Component
)
from ..config import ReportConfig

logger = logging.getLogger(__name__)


class WorklogProcessor:
    """Process and aggregate worklog data"""
    
    def __init__(self, config: ReportConfig):
        self.config = config
    
    def process_issues(
        self,
        issues: List[Issue],
        project_key: str,
        start_date: datetime,
        end_date: datetime,
        filter_author: Author = None
    ) -> List[TimeEntry]:
        """Process issues and create time entries (optimized single-pass)"""
        
        # Use a single dict to aggregate directly: (project_component, author, work_type) -> TimeEntry
        aggregated = {}
        
        for issue in issues:
            for component in issue.components:
                project_component = ProjectComponent(
                    project=project_key,
                    component=component
                )
                
                for worklog in issue.worklogs:
                    # Filter by author if specified (using Author equality)
                    if filter_author and worklog.author != filter_author:
                        continue
                    
                    # Filter by date range
                    if not (start_date <= worklog.started <= end_date):
                        continue
                    
                    # Create aggregation key
                    key = (project_component, worklog.author, issue.work_type)
                    
                    # Add or update entry
                    if key in aggregated:
                        aggregated[key].add_hours(worklog.hours, issue.key)
                    else:
                        aggregated[key] = TimeEntry(
                            project_component=project_component,
                            author=worklog.author,
                            hours=worklog.hours,
                            work_type=issue.work_type,
                            issues=[issue.key]
                        )
        
        return list(aggregated.values())
    
    def aggregate_entries(self, entries: List[TimeEntry]) -> Dict[tuple, TimeEntry]:
        """Aggregate time entries by project-component-author-worktype (optimized)"""
        
        aggregated = {}
        
        for entry in entries:
            key = (
                entry.project_component,
                entry.author,
                entry.work_type
            )
            
            if key in aggregated:
                # Merge hours and issues
                aggregated[key].hours += entry.hours
                # Add unique issues only
                for issue in entry.issues:
                    if issue not in aggregated[key].issues:
                        aggregated[key].issues.append(issue)
            else:
                aggregated[key] = entry
        
        return aggregated
    
    def create_monthly_report(
        self,
        project_keys: List[str],
        year: int,
        month: int,
        entries: List[TimeEntry]
    ) -> MonthlyReport:
        """Create monthly report from time entries"""
        
        return MonthlyReport(
            year=year,
            month=month,
            project_keys=project_keys,
            entries=entries
        )
    
    def create_yearly_report(
        self,
        project_keys: List[str],
        year: int,
        monthly_reports: List[MonthlyReport]
    ) -> YearlyReport:
        """Create yearly report from monthly reports"""
        
        return YearlyReport(
            year=year,
            project_keys=project_keys,
            monthly_reports=monthly_reports
        )
    
    def get_csv_data(
        self,
        entries: List[TimeEntry]
    ) -> Dict[ProjectComponent, Dict[Author, float]]:
        """Prepare data for CSV export"""
        
        # Structure: {ProjectComponent: {Author: hours}}
        csv_data = defaultdict(lambda: defaultdict(float))
        
        for entry in entries:
            csv_data[entry.project_component][entry.author] += entry.hours
        
        return dict(csv_data)
