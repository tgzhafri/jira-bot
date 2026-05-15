"""
Data models for Automate Jira and Confluence backup operations.

Re-exports all models from the original Jira models module and the
Confluence Cloud backup models module.
"""

# Re-export all original Jira models for backward compatibility
from ._models import (
    Author,
    Component,
    Issue,
    MonthlyReport,
    ProjectComponent,
    TimeEntry,
    WorkType,
    Worklog,
    YearlyReport,
)

# Export Confluence Cloud backup models
from .confluence_models import (
    BackupAttachment,
    BackupPage,
    SpaceBackupResult,
)

__all__ = [
    # Jira models
    "Author",
    "Component",
    "Issue",
    "MonthlyReport",
    "ProjectComponent",
    "TimeEntry",
    "WorkType",
    "Worklog",
    "YearlyReport",
    # Confluence models
    "BackupAttachment",
    "BackupPage",
    "SpaceBackupResult",
]
