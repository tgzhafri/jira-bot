"""
Report generation module for Jira time tracking
"""

import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
from enum import Enum
import time

from .config import Config
from .jira_client import JiraClient, JiraClientError
from .processors import WorklogProcessor
from .exporters import (
    YearlyOverviewExporter,
    QuarterlyBreakdownExporter,
    MonthlyBreakdownExporter,
    WeeklyBreakdownExporter
)
from .utils import get_month_range, format_date_for_jql
from .models import YearlyReport, MonthlyReport

logger = logging.getLogger(__name__)

# Malaysia timezone (UTC+8)
MALAYSIA_TZ = timezone(timedelta(hours=8))


class ReportType(Enum):
    """Enum for report types"""
    YEARLY = "yearly"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"


class ReportConfig:
    """Configuration for report generation"""
    
    EXPORTER_MAP = {
        ReportType.YEARLY: YearlyOverviewExporter,
        ReportType.QUARTERLY: QuarterlyBreakdownExporter,
        ReportType.MONTHLY: MonthlyBreakdownExporter,
        ReportType.WEEKLY: WeeklyBreakdownExporter
    }
    
    DEFAULT_FILENAMES = {
        ReportType.YEARLY: "manhour_report_{year}.csv",
        ReportType.QUARTERLY: "quarterly_report_{year}.csv",
        ReportType.MONTHLY: "monthly_breakdown_{year}.csv",
        ReportType.WEEKLY: "weekly_breakdown_{year}.csv"
    }
    
    @classmethod
    def get_exporter_class(cls, report_type: ReportType):
        """Get exporter class for report type"""
        return cls.EXPORTER_MAP[report_type]
    
    @classmethod
    def get_default_filename(cls, report_type: ReportType, year: int) -> str:
        """Get default filename for report type"""
        return cls.DEFAULT_FILENAMES[report_type].format(year=year)


def fetch_month_project_data(
    client: JiraClient,
    processor: WorklogProcessor,
    project_key: str,
    year: int,
    month: int,
    filter_author=None
) -> Tuple[str, int, List]:
    """Fetch and process data for a single month-project combination"""
    try:
        start_date, end_date = get_month_range(year, month)
        start_str = format_date_for_jql(start_date)
        end_str = format_date_for_jql(end_date)

        # Fetch issues (filtered by user email if specified)
        filter_user_email = filter_author.email if filter_author and filter_author.email else None
        raw_issues = client.get_issues_with_worklog(
            project_key,
            start_str,
            end_str,
            filter_user=filter_user_email
        )

        # Parse issues - fetch all worklogs to get all team members
        issues = [client.parse_issue(raw, fetch_all_worklogs=True) for raw in raw_issues]

        # Process into time entries (filter by author if specified)
        entries = processor.process_issues(
            issues,
            project_key,
            start_date,
            end_date,
            filter_author=filter_author
        )

        logger.info(f"✓ {project_key} {year}-{month:02d}: {len(entries)} entries")
        return (project_key, month, entries)

    except JiraClientError as e:
        logger.warning(f"Failed to process {project_key} for {year}-{month:02d}: {e}")
        return (project_key, month, [])


def _fetch_data_parallel(
    client: JiraClient,
    processor: WorklogProcessor,
    project_keys: List[str],
    year: int,
    max_workers: int,
    preserve_months: bool = False
) -> dict:
    """Fetch data in parallel for all month-project combinations
    
    Args:
        preserve_months: If True, returns dict with month keys. If False, returns flat list.
    """
    # Create tasks for all month-project combinations
    tasks = []
    for month in range(1, 13):
        for project_key in project_keys:
            tasks.append((project_key, year, month))

    logger.info(f"Processing {len(tasks)} month-project combinations in parallel...")
    fetch_start = time.time()

    # Store entries by month if needed
    if preserve_months:
        entries_by_month = {month: [] for month in range(1, 13)}
    else:
        all_entries = []

    # Execute tasks in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(fetch_month_project_data, client, processor, pk, y, m, None): (pk, m)
            for pk, y, m in tasks
        }

        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_task):
            project_key, month = future_to_task[future]
            completed += 1
            try:
                _, result_month, entries = future.result()
                if preserve_months:
                    entries_by_month[result_month].extend(entries)
                else:
                    all_entries.extend(entries)
                logger.info(f"Progress: {completed}/{len(tasks)} completed")
            except Exception as e:
                logger.error(f"Task failed for {project_key} {year}-{month:02d}: {e}")

    fetch_time = time.time() - fetch_start
    logger.info(f"✓ Data fetching completed in {fetch_time:.1f}s")

    return entries_by_month if preserve_months else all_entries


def _initialize_client_and_processor(config: Config):
    """Initialize Jira client and worklog processor"""
    client = JiraClient(
        config.jira,
        enable_cache=config.jira.enable_cache,
        cache_dir=config.jira.cache_dir
    )
    processor = WorklogProcessor(config.report)
    
    # Test connection
    if not client.test_connection():
        logger.error("Failed to connect to Jira")
        return None, None
    
    return client, processor


def _get_project_keys(config: Config, client: JiraClient) -> Optional[List[str]]:
    """Get project keys from config or fetch all accessible projects"""
    if config.jira.project_keys is None:
        logger.info("No projects specified, fetching all accessible projects...")
        project_keys = client.get_all_projects()
        if not project_keys:
            logger.error("No projects found")
            return None
    else:
        project_keys = config.jira.project_keys
    
    logger.info(f"Projects: {', '.join(project_keys)}")
    return project_keys


def _create_yearly_report_from_entries(
    entries_data,
    year: int,
    project_keys: List[str],
    preserve_months: bool = False
) -> YearlyReport:
    """Create YearlyReport object from entries data
    
    Args:
        entries_data: Either a list of entries (preserve_months=False) or dict of month->entries
        preserve_months: Whether entries_data is organized by month
    """
    if preserve_months:
        # Create monthly reports with entries
        monthly_reports = []
        for month in range(1, 13):
            monthly_report = MonthlyReport(
                year=year,
                month=month,
                project_keys=project_keys,
                entries=entries_data[month]
            )
            monthly_reports.append(monthly_report)
    else:
        # Create a single dummy monthly report for yearly overview
        dummy_report = MonthlyReport(
            year=year,
            month=1,
            project_keys=project_keys,
            entries=entries_data
        )
        monthly_reports = [dummy_report]
    
    return YearlyReport(
        year=year,
        project_keys=project_keys,
        monthly_reports=monthly_reports
    )


def generate_report(
    config: Config,
    report_type: ReportType,
    year: int = None,
    output_file: str = None,
    max_workers: int = None
):
    """Unified report generation function
    
    Args:
        config: Configuration object
        report_type: Type of report to generate
        year: Report year (defaults to current year)
        output_file: Output file path (defaults to standard naming)
        max_workers: Number of parallel workers (defaults to config value)
    
    Returns:
        For yearly reports: Path to CSV file
        For other reports: Tuple of (csv_path, xlsx_path)
    """
    # Set defaults
    if year is None:
        year = datetime.now().year
    if max_workers is None:
        max_workers = config.jira.max_workers
    if output_file is None:
        output_file = f"reports/{ReportConfig.get_default_filename(report_type, year)}"

    logger.info(f"Generating {report_type.value} report for {year}")

    # Initialize components
    client, processor = _initialize_client_and_processor(config)
    if not client or not processor:
        return None

    # Get project keys
    project_keys = _get_project_keys(config, client)
    if not project_keys:
        return None

    logger.info(f"Using parallel processing with {max_workers} workers")
    logger.info(f"Cache: {'enabled' if config.jira.enable_cache else 'disabled'}")

    # Start timing
    start_time = time.time()

    # Fetch data - preserve months for all except yearly overview
    preserve_months = report_type != ReportType.YEARLY
    entries_data = _fetch_data_parallel(
        client, processor, project_keys, year, max_workers, preserve_months
    )

    # Check if we have data
    if preserve_months:
        has_data = any(entries_data.values())
    else:
        has_data = bool(entries_data)
    
    if not has_data:
        logger.warning("No data found for the specified period")
        return None

    # Export report
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_start = time.time()

    # For yearly overview, aggregate entries first
    if report_type == ReportType.YEARLY:
        agg_start = time.time()
        aggregated = processor.aggregate_entries(entries_data)
        agg_time = time.time() - agg_start
        logger.info(f"✓ Data aggregation completed in {agg_time:.1f}s")
        
        # Log unique team members
        unique_authors = set(entry.author for entry in aggregated.values())
        logger.info(f"Found {len(unique_authors)} unique team members:")
        for author in sorted(unique_authors, key=lambda a: a.display_name):
            logger.info(f"  - {author.display_name} ({author.email})")
        
        entries_data = list(aggregated.values())

    # Create yearly report with timestamp metadata
    yearly_report = _create_yearly_report_from_entries(
        entries_data, year, project_keys, preserve_months
    )
    
    # Add timestamp metadata (Malaysia time)
    yearly_report.fetch_timestamp = datetime.now(MALAYSIA_TZ)
    yearly_report.from_cache = client.is_using_cache()
    yearly_report.cache_timestamp = client.get_cache_timestamp()

    # Export using appropriate exporter
    exporter_class = ReportConfig.get_exporter_class(report_type)
    exporter = exporter_class(output_path, filter_active_only=True)
    result = exporter.export_yearly(yearly_report)

    export_time = time.time() - export_start
    total_time = time.time() - start_time

    # Log results
    if report_type == ReportType.YEARLY:
        logger.info(f"✅ CSV report generated: {result}")
    else:
        csv_path, xlsx_path = result
        logger.info(f"✅ Reports generated:")
        logger.info(f"   CSV: {csv_path}")
        if xlsx_path:
            logger.info(f"   XLSX: {xlsx_path}")
    
    logger.info(f"⏱️  Performance: Export={export_time:.1f}s, Total={total_time:.1f}s")

    return result


# Convenience functions for backward compatibility
def generate_csv_report(config: Config, year: int = None, output_file: str = None, max_workers: int = None):
    """Generate CSV team overview report"""
    return generate_report(config, ReportType.YEARLY, year, output_file, max_workers)


def generate_quarterly_report(config: Config, year: int = None, output_file: str = None, max_workers: int = None):
    """Generate CSV quarterly breakdown report"""
    return generate_report(config, ReportType.QUARTERLY, year, output_file, max_workers)


def generate_monthly_breakdown_report(config: Config, year: int = None, output_file: str = None, max_workers: int = None):
    """Generate CSV monthly breakdown report"""
    return generate_report(config, ReportType.MONTHLY, year, output_file, max_workers)


def generate_weekly_breakdown_report(config: Config, year: int = None, output_file: str = None, max_workers: int = None):
    """Generate CSV weekly breakdown report"""
    return generate_report(config, ReportType.WEEKLY, year, output_file, max_workers)
