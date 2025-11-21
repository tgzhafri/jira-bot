"""
Data models for Automate Jira
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum


class WorkType(Enum):
    """Work type classification"""
    DEVELOPMENT = "Development"
    MAINTENANCE = "Maintenance"
    UNCLASSIFIED = "Unclassified"


@dataclass
class Author:
    """Worklog author information"""
    email: str
    display_name: str
    account_id: Optional[str] = None
    active: bool = True  # User active status from Jira API
    
    def __hash__(self):
        # Use account_id if available, otherwise use email+display_name
        if self.account_id:
            return hash(self.account_id)
        return hash((self.email, self.display_name))
    
    def __eq__(self, other):
        if isinstance(other, Author):
            # Compare by account_id if both have it
            if self.account_id and other.account_id:
                return self.account_id == other.account_id
            # Otherwise compare by email and display_name
            return self.email == other.email and self.display_name == other.display_name
        return False


@dataclass
class Component:
    """Jira component"""
    name: str
    id: Optional[str] = None
    description: Optional[str] = None
    
    def __hash__(self):
        return hash(self.name)


@dataclass
class Worklog:
    """Individual worklog entry"""
    id: str
    author: Author
    time_spent_seconds: int
    started: datetime
    issue_key: str
    comment: Optional[str] = None
    
    @property
    def hours(self) -> float:
        """Get hours from time spent"""
        return self.time_spent_seconds / 3600
    
    @property
    def week_number(self) -> int:
        """Get week number within month (1-5)"""
        week = ((self.started.day - 1) // 7) + 1
        return min(week, 5)


@dataclass
class Issue:
    """Jira issue"""
    key: str
    summary: str
    issue_type: str
    components: List[Component]
    labels: List[str]
    work_type: WorkType
    worklogs: List[Worklog] = field(default_factory=list)
    custom_fields: Dict[str, any] = field(default_factory=dict)
    
    def get_total_hours(self) -> float:
        """Get total hours for this issue"""
        return sum(wl.hours for wl in self.worklogs)
    
    def get_hours_by_author(self) -> Dict[Author, float]:
        """Get hours grouped by author"""
        hours_by_author = {}
        for worklog in self.worklogs:
            author = worklog.author
            hours_by_author[author] = hours_by_author.get(author, 0) + worklog.hours
        return hours_by_author


@dataclass
class ProjectComponent:
    """Project-Component combination"""
    project: str
    component: Component
    
    def __hash__(self):
        return hash((self.project, self.component.name))
    
    def __eq__(self, other):
        if isinstance(other, ProjectComponent):
            return self.project == other.project and self.component.name == other.component.name
        return False
    
    def __str__(self):
        return f"{self.project} - {self.component.name}"


@dataclass
class TimeEntry:
    """Aggregated time entry"""
    project_component: ProjectComponent
    author: Author
    hours: float
    work_type: WorkType
    issues: List[str] = field(default_factory=list)
    week_hours: Dict[int, float] = field(default_factory=dict)  # week_number -> hours
    
    def add_hours(self, hours: float, issue_key: Optional[str] = None, week: Optional[int] = None):
        """Add hours to this entry"""
        self.hours += hours
        if issue_key and issue_key not in self.issues:
            self.issues.append(issue_key)
        if week is not None:
            self.week_hours[week] = self.week_hours.get(week, 0) + hours


@dataclass
class MonthlyReport:
    """Monthly time tracking report"""
    year: int
    month: int
    project_keys: List[str]
    entries: List[TimeEntry]
    
    @property
    def month_name(self) -> str:
        """Get month name"""
        return datetime(self.year, self.month, 1).strftime('%B')
    
    def get_total_hours(self) -> float:
        """Get total hours for the month"""
        return sum(entry.hours for entry in self.entries)
    
    def get_hours_by_work_type(self) -> Dict[WorkType, float]:
        """Get hours grouped by work type"""
        hours_by_type = {}
        for entry in self.entries:
            work_type = entry.work_type
            hours_by_type[work_type] = hours_by_type.get(work_type, 0) + entry.hours
        return hours_by_type
    
    def get_hours_by_author(self) -> Dict[Author, float]:
        """Get hours grouped by author"""
        hours_by_author = {}
        for entry in self.entries:
            author = entry.author
            hours_by_author[author] = hours_by_author.get(author, 0) + entry.hours
        return hours_by_author


@dataclass
class YearlyReport:
    """Yearly time tracking report"""
    year: int
    project_keys: List[str]
    monthly_reports: List[MonthlyReport]
    
    def get_total_hours(self) -> float:
        """Get total hours for the year"""
        return sum(report.get_total_hours() for report in self.monthly_reports)
    
    def get_hours_by_work_type(self) -> Dict[WorkType, float]:
        """Get hours grouped by work type"""
        hours_by_type = {}
        for report in self.monthly_reports:
            for work_type, hours in report.get_hours_by_work_type().items():
                hours_by_type[work_type] = hours_by_type.get(work_type, 0) + hours
        return hours_by_type
    
    def get_hours_by_author(self) -> Dict[Author, float]:
        """Get hours grouped by author"""
        hours_by_author = {}
        for report in self.monthly_reports:
            for author, hours in report.get_hours_by_author().items():
                hours_by_author[author] = hours_by_author.get(author, 0) + hours
        return hours_by_author
    
    @property
    def months_with_data(self) -> int:
        """Count months with data"""
        return len([r for r in self.monthly_reports if r.get_total_hours() > 0])
