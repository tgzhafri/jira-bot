#!/usr/bin/env python3
"""
CLI script for generating Jira time tracking reports
"""

import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.jira_client import JiraClientError
from src.report_generator import generate_csv_report, generate_quarterly_report
from src.utils import setup_logging

logger = logging.getLogger(__name__)


def main():
    """Main entry point for CLI"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate Jira time tracking reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate yearly overview report
  python scripts/generate_report.py
  
  # Generate quarterly breakdown report
  python scripts/generate_report.py --quarterly
  
  # Generate report for specific year
  python scripts/generate_report.py --year 2024
  
  # Generate quarterly report for 2024
  python scripts/generate_report.py --quarterly --year 2024
        """
    )
    
    parser.add_argument(
        '--quarterly',
        action='store_true',
        help='Generate quarterly breakdown report instead of yearly overview'
    )
    
    parser.add_argument(
        '--year',
        type=int,
        default=datetime.now().year,
        help='Report year (default: current year)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path (default: reports/manhour_report_YYYY.csv or reports/quarterly_report_YYYY.csv)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level, verbose=args.verbose)
    
    try:
        # Load configuration
        config = Config.from_env()
        config.validate()
        
        # Generate report based on type
        if args.quarterly:
            logger.info(f"Generating quarterly breakdown report for {args.year}")
            generate_quarterly_report(
                config,
                year=args.year,
                output_file=args.output
            )
        else:
            logger.info(f"Generating yearly overview report for {args.year}")
            generate_csv_report(
                config,
                year=args.year,
                output_file=args.output
            )
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except JiraClientError as e:
        logger.error(f"Jira error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
