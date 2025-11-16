"""
Date utility functions
"""

from datetime import datetime, timedelta
from typing import Tuple


def get_month_range(year: int, month: int) -> Tuple[datetime, datetime]:
    """Get start and end datetime for a month (timezone-aware UTC)"""
    from datetime import timezone
    
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    
    # Set end time to end of day
    end_date = end_date.replace(hour=23, minute=59, second=59)
    
    return start_date, end_date


def get_year_range(year: int) -> Tuple[datetime, datetime]:
    """Get start and end datetime for a year (timezone-aware UTC)"""
    from datetime import timezone
    
    start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    return start_date, end_date


def format_date_for_jql(dt: datetime) -> str:
    """Format datetime for JQL query"""
    return dt.strftime('%Y-%m-%d')


def get_week_number(date: datetime) -> int:
    """Get week number within month (1-5)"""
    week = ((date.day - 1) // 7) + 1
    return min(week, 5)
