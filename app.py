#!/usr/bin/env python3
"""
Streamlit web UI for Automate Jira
"""

import streamlit as st
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.report_generator import (
    generate_csv_report,
    generate_quarterly_report,
    generate_monthly_breakdown_report,
    generate_weekly_breakdown_report,
    ReportType
)
from src.ui import show_config_error
from src.ui.sidebar import render_sidebar
from src.ui.report_view import display_stored_report
from src.ui.state_manager import initialize_session_state

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Report Generation Logic
# ============================================================================

def generate_report_by_type(config: Config, report_type: str, year: int, max_workers: int):
    """Generate report based on selected type
    
    Returns:
        Tuple of (result_path, xlsx_path) or None if failed
    """
    Path("reports").mkdir(exist_ok=True)
    
    report_generators = {
        "Yearly Overview": lambda: generate_csv_report(
            config, year=year, 
            output_file=f"reports/manhour_report_{year}.csv",
            max_workers=max_workers
        ),
        "Quarterly Breakdown": lambda: generate_quarterly_report(
            config, year=year,
            output_file=f"reports/quarterly_report_{year}.csv",
            max_workers=max_workers
        ),
        "Monthly Breakdown": lambda: generate_monthly_breakdown_report(
            config, year=year,
            output_file=f"reports/monthly_breakdown_{year}.csv",
            max_workers=max_workers
        ),
        "Weekly Breakdown": lambda: generate_weekly_breakdown_report(
            config, year=year,
            output_file=f"reports/weekly_breakdown_{year}.csv",
            max_workers=max_workers
        )
    }
    
    result = report_generators[report_type]()
    
    # Handle different return types
    if report_type == "Yearly Overview":
        return (result, None) if result else None
    else:
        return result if result else None


def handle_report_generation(config: Config, report_type: str, year: int, max_workers: int):
    """Handle report generation with progress indicators"""
    report_name = {
        "Yearly Overview": "yearly overview",
        "Quarterly Breakdown": "quarterly breakdown",
        "Monthly Breakdown": "monthly breakdown",
        "Weekly Breakdown": "weekly breakdown"
    }[report_type]
    
    with st.spinner(f"Generating {report_name} report for {year}..."):
        try:
            progress_text = st.empty()
            progress_bar = st.progress(0)
            
            progress_text.text("Fetching data from Jira...")
            progress_bar.progress(30)
            
            result = generate_report_by_type(config, report_type, year, max_workers)
            
            # Clear progress indicators
            progress_bar.empty()
            progress_text.empty()
            
            if result:
                csv_path, xlsx_path = result
                if csv_path and Path(csv_path).exists():
                    # Store in session state
                    st.session_state.report_generated = True
                    st.session_state.csv_path = csv_path
                    st.session_state.xlsx_path = xlsx_path
                    st.session_state.report_type = report_type
                    
                    # Read CSV data
                    with open(csv_path, 'rb') as f:
                        st.session_state.csv_data = f.read()
                else:
                    st.warning(":warning: No data found for the specified period")
            else:
                st.warning(":warning: No data found for the specified period")
                
        except Exception as e:
            st.error(f":x: Error generating report: {e}")
            logger.exception("Report generation failed")


# ============================================================================
# Configuration & Cache Management
# ============================================================================

def load_and_validate_config(use_cache: bool, max_workers: int):
    """Load and validate configuration"""
    try:
        config = Config.from_env()
        config.jira.enable_cache = use_cache
        config.jira.max_workers = max_workers
        
        # Ensure cache directory is absolute path
        if not Path(config.jira.cache_dir).is_absolute():
            config.jira.cache_dir = str(Path.cwd() / config.jira.cache_dir)
        
        config.validate()
        return config
        
    except ValueError as e:
        show_config_error(str(e))
        return None
    except Exception as e:
        st.error(f":x: Configuration error: {e}")
        st.stop()
        return None


def display_connection_status(config: Config):
    """Display connection status and cache info"""
    cache_path = Path(config.jira.cache_dir)
    cache_files = list(cache_path.glob("*.json")) if cache_path.exists() else []
    
    if config.jira.enable_cache and cache_files:
        cache_status = f"{len(cache_files)} cached"
    elif not config.jira.enable_cache:
        cache_status = "disabled"
    else:
        cache_status = "empty"
    
    st.info(f":link: Connected: {config.jira.url} | :floppy_disk: Cache: {cache_status}")


def handle_cache_clearing(config: Config):
    """Clear cache if requested"""
    cache_path = Path(config.jira.cache_dir)
    if cache_path.exists() and cache_path.is_dir():
        import shutil
        for item in cache_path.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        st.success(":white_check_mark: Cache cleared!")
        st.rerun()
    else:
        st.info("Cache directory does not exist")


# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main application entry point"""
    
    try:
        # Page config
        st.set_page_config(
            page_title="Automate Jira",
            page_icon=":bar_chart:",
            layout="wide"
        )
        
        # Header
        st.title(":bar_chart: Automate Jira")
        st.markdown("Generate CSV reports of team hours by project and component")
    except Exception as e:
        st.error(f":x: Error initializing page: {e}")
        logger.exception("Page initialization failed")
        return
    
    # Initialize session state
    initialize_session_state()
    
    # Render sidebar and get settings
    report_type, year, max_workers, use_cache, clear_cache_clicked = render_sidebar()
    
    st.markdown("---")
    
    # Load and validate configuration
    config = load_and_validate_config(use_cache, max_workers)
    if not config:
        return
    
    # Display connection status
    display_connection_status(config)
    
    # Handle cache clearing
    if clear_cache_clicked:
        handle_cache_clearing(config)
    
    # Generate button
    if st.button(":rocket: Generate Report", type="primary", use_container_width=True):
        handle_report_generation(config, report_type, year, max_workers)
    
    # Display report if it exists and matches current selection
    if st.session_state.report_type == report_type:
        display_stored_report()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        Built using Streamlit | Automate Jira v1.0.0
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
