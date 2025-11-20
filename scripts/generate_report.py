#!/usr/bin/env python3
"""
CLI script for generating Jira time tracking reports
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.jira_client import JiraClientError
from src.report_generator import generate_csv_report
from src.utils import setup_logging

logger = logging.getLogger(__name__)


def main():
    """Main entry point for CLI"""
    
    # Setup logging
    setup_logging(level="INFO", verbose=False)
    
    try:
        # Load configuration
        config = Config.from_env()
        config.validate()
        
        # Generate report
        current_year = datetime.now().year
        generate_csv_report(config, year=current_year)
        
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
