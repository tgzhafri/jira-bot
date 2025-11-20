"""
Report generation module for Jira time tracking
"""

import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import time

from .config import Config
from .jira_client import JiraClient, JiraClientError
from .processors import WorklogProcessor
from .exporters import YearlyOverviewExporter
from .utils import get_month_range, format_date_for_jql
from .models import YearlyReport, MonthlyReport

logger = logging.getLogger(__name__)


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


def generate_csv_report(
    config: Config,
    year: int = None,
    output_file: str = None,
    max_workers: int = None
):
    """Generate CSV team overview report with parallel processing

    Args:
        config: Configuration object
        year: Report year
        output_file: Output file path
        max_workers: Number of parallel workers
    """

    if year is None:
        year = datetime.now().year

    if max_workers is None:
        max_workers = config.jira.max_workers

    logger.info(f"Generating CSV team overview report for {year}")

    # Initialize components with cache settings from config
    client = JiraClient(
        config.jira,
        enable_cache=config.jira.enable_cache,
        cache_dir=config.jira.cache_dir
    )
    processor = WorklogProcessor(config.report)

    # Test connection
    if not client.test_connection():
        logger.error("Failed to connect to Jira")
        return None

    # Get project keys - fetch all if not specified
    if config.jira.project_keys is None:
        logger.info("No projects specified, fetching all accessible projects...")
        project_keys = client.get_all_projects()
        if not project_keys:
            logger.error("No projects found")
            return None
    else:
        project_keys = config.jira.project_keys

    logger.info(f"Projects: {', '.join(project_keys)}")
    logger.info(f"Using parallel processing with {max_workers} workers")
    logger.info(f"Cache: {'enabled' if config.jira.enable_cache else 'disabled'}")

    # Start timing
    start_time = time.time()

    # Collect all entries for the year using parallel processing
    all_entries = []

    # Create tasks for all month-project combinations
    tasks = []
    for month in range(1, 13):
        for project_key in project_keys:
            tasks.append((project_key, year, month))

    logger.info(f"Processing {len(tasks)} month-project combinations in parallel...")
    fetch_start = time.time()

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
                all_entries.extend(entries)
                logger.info(f"Progress: {completed}/{len(tasks)} completed")
            except Exception as e:
                logger.error(f"Task failed for {project_key} {year}-{month:02d}: {e}")

    fetch_time = time.time() - fetch_start
    logger.info(f"✓ Data fetching completed in {fetch_time:.1f}s")

    # Check if we have data
    if not all_entries:
        logger.warning("No data found for the specified period")
        return None

    # Export to CSV
    if output_file is None:
        output_file = f"reports/manhour_report_{year}.csv"

    output_path = Path(output_file)
    # Ensure reports directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_start = time.time()

    # Aggregate entries
    agg_start = time.time()
    aggregated = processor.aggregate_entries(all_entries)
    agg_time = time.time() - agg_start
    logger.info(f"✓ Data aggregation completed in {agg_time:.1f}s")

    # Log unique team members found
    unique_authors_found = set(entry.author for entry in aggregated.values())
    logger.info(f"Found {len(unique_authors_found)} unique team members:")
    for author in sorted(unique_authors_found, key=lambda a: a.display_name):
        logger.info(f"  - {author.display_name} ({author.email})")

    # Create yearly report
    yearly_report = YearlyReport(
        year=year,
        project_keys=project_keys,
        monthly_reports=[]
    )

    # Manually add entries to a dummy monthly report for export
    dummy_report = MonthlyReport(
        year=year,
        month=1,
        project_keys=project_keys,
        entries=list(aggregated.values())
    )
    yearly_report.monthly_reports = [dummy_report]

    exporter = YearlyOverviewExporter(output_path, filter_active_only=True)
    result_path = exporter.export_yearly(yearly_report)

    export_time = time.time() - export_start
    total_time = time.time() - start_time

    logger.info(f"✅ CSV report generated: {result_path}")
    logger.info(f"⏱️  Performance: Fetch={fetch_time:.1f}s, Export={export_time:.1f}s, Total={total_time:.1f}s")

    return result_path



def generate_quarterly_report(
    config: Config,
    year: int = None,
    output_file: str = None,
    max_workers: int = None
):
    """Generate CSV quarterly breakdown report with parallel processing

    Args:
        config: Configuration object
        year: Report year
        output_file: Output file path
        max_workers: Number of parallel workers
    """

    if year is None:
        year = datetime.now().year

    if max_workers is None:
        max_workers = config.jira.max_workers

    logger.info(f"Generating CSV quarterly breakdown report for {year}")

    # Initialize components with cache settings from config
    client = JiraClient(
        config.jira,
        enable_cache=config.jira.enable_cache,
        cache_dir=config.jira.cache_dir
    )
    processor = WorklogProcessor(config.report)

    # Test connection
    if not client.test_connection():
        logger.error("Failed to connect to Jira")
        return None

    # Get project keys - fetch all if not specified
    if config.jira.project_keys is None:
        logger.info("No projects specified, fetching all accessible projects...")
        project_keys = client.get_all_projects()
        if not project_keys:
            logger.error("No projects found")
            return None
    else:
        project_keys = config.jira.project_keys

    logger.info(f"Projects: {', '.join(project_keys)}")
    logger.info(f"Using parallel processing with {max_workers} workers")
    logger.info(f"Cache: {'enabled' if config.jira.enable_cache else 'disabled'}")

    # Start timing
    start_time = time.time()

    # Create tasks for all month-project combinations
    tasks = []
    for month in range(1, 13):
        for project_key in project_keys:
            tasks.append((project_key, year, month))

    logger.info(f"Processing {len(tasks)} month-project combinations in parallel...")
    fetch_start = time.time()

    # Store entries by month to preserve month information
    entries_by_month = {month: [] for month in range(1, 13)}

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
                entries_by_month[result_month].extend(entries)
                logger.info(f"Progress: {completed}/{len(tasks)} completed")
            except Exception as e:
                logger.error(f"Task failed for {project_key} {year}-{month:02d}: {e}")

    fetch_time = time.time() - fetch_start
    logger.info(f"✓ Data fetching completed in {fetch_time:.1f}s")

    # Check if we have data
    if not any(entries_by_month.values()):
        logger.warning("No data found for the specified period")
        return None

    # Export to CSV
    if output_file is None:
        output_file = f"reports/quarterly_report_{year}.csv"

    output_path = Path(output_file)
    # Ensure reports directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_start = time.time()

    # Create monthly reports with entries
    monthly_reports = []
    for month in range(1, 13):
        monthly_report = MonthlyReport(
            year=year,
            month=month,
            project_keys=project_keys,
            entries=entries_by_month[month]
        )
        monthly_reports.append(monthly_report)
    
    yearly_report = YearlyReport(
        year=year,
        project_keys=project_keys,
        monthly_reports=monthly_reports
    )
    
    # Use quarterly exporter
    from .exporters import QuarterlyBreakdownExporter
    exporter = QuarterlyBreakdownExporter(output_path, filter_active_only=True)
    result_paths = exporter.export_yearly(yearly_report)
    
    # result_paths is a tuple (csv_path, xlsx_path)
    csv_path, xlsx_path = result_paths

    export_time = time.time() - export_start
    total_time = time.time() - start_time

    logger.info(f"✅ Quarterly reports generated:")
    logger.info(f"   CSV: {csv_path}")
    if xlsx_path:
        logger.info(f"   XLSX: {xlsx_path}")
    logger.info(f"⏱️  Performance: Fetch={fetch_time:.1f}s, Export={export_time:.1f}s, Total={total_time:.1f}s")

    return result_paths
