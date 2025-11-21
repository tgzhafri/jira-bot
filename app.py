#!/usr/bin/env python3
"""
Streamlit web UI for Automate Jira
"""

import streamlit as st
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.report_generator import (
    generate_csv_report,
    generate_quarterly_report,
    generate_monthly_breakdown_report,
    generate_weekly_breakdown_report
)
from src.ui import show_config_error, display_report_preview

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
# Report Display
# ============================================================================

def display_download_buttons(csv_path: str, xlsx_path: str, csv_data: bytes, report_type: str):
    """Display download buttons based on report type"""
    has_xlsx = report_type in ["Quarterly Breakdown", "Monthly Breakdown", "Weekly Breakdown"]
    
    if has_xlsx and xlsx_path and Path(xlsx_path).exists():
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label=":inbox_tray: Download CSV",
                data=csv_data,
                file_name=Path(csv_path).name,
                mime="text/csv",
                use_container_width=True,
                key="download_csv"
            )
        with col2:
            with open(xlsx_path, 'rb') as f:
                xlsx_data = f.read()
            st.download_button(
                label=":inbox_tray: Download XLSX (Formatted)",
                data=xlsx_data,
                file_name=Path(xlsx_path).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_xlsx"
            )
    else:
        st.download_button(
            label=":inbox_tray: Download CSV Report",
            data=csv_data,
            file_name=Path(csv_path).name,
            mime="text/csv",
            use_container_width=True,
            key="download_csv"
        )


def display_stored_report():
    """Display report from session state if available"""
    if not st.session_state.report_generated or not st.session_state.csv_path:
        return
    
    csv_path = st.session_state.csv_path
    xlsx_path = st.session_state.xlsx_path
    csv_data = st.session_state.csv_data
    report_type = st.session_state.report_type
    
    # Only display if file exists
    if not Path(csv_path).exists():
        return
    
    # Show download buttons
    display_download_buttons(csv_path, xlsx_path, csv_data, report_type)
    
    # Display preview based on report type
    report_type_map = {
        "Yearly Overview": "yearly",
        "Quarterly Breakdown": "quarterly",
        "Monthly Breakdown": "monthly",
        "Weekly Breakdown": "weekly"
    }
    
    preview_type = report_type_map.get(report_type, "yearly")
    xlsx_path_obj = Path(xlsx_path) if xlsx_path else None
    
    display_report_preview(Path(csv_path), csv_data, preview_type, xlsx_path_obj)


# ============================================================================
# Sidebar Configuration
# ============================================================================

def render_sidebar():
    """Render sidebar configuration and return settings"""
    st.sidebar.header(":gear: Configuration")
    
    # Report type selector
    report_type = st.sidebar.radio(
        "Report Type",
        options=["Yearly Overview", "Quarterly Breakdown", "Monthly Breakdown", "Weekly Breakdown"],
        index=0,
        help="Choose report type: yearly summary, quarterly breakdown, monthly breakdown, or weekly breakdown per team member"
    )
    
    current_year = datetime.now().year
    year = st.sidebar.number_input(
        "Report Year",
        min_value=2020,
        max_value=current_year + 1,
        value=current_year,
        step=1
    )
    
    with st.sidebar.expander("Advanced Options"):
        max_workers = st.slider(
            "Parallel Workers",
            min_value=1,
            max_value=16,
            value=8,
            help="Number of parallel threads for fetching data"
        )
        
        use_cache = st.checkbox(
            "Enable Cache",
            value=True,
            help="Cache API responses for faster subsequent runs"
        )
        
        clear_cache_clicked = st.button(
            ":wastebasket: Clear Cache",
            help="Delete all cached API responses"
        )
    
    return report_type, year, max_workers, use_cache, clear_cache_clicked


# ============================================================================
# Main Application
# ============================================================================

def initialize_session_state():
    """Initialize session state variables"""
    if 'report_generated' not in st.session_state:
        st.session_state.report_generated = False
    if 'csv_path' not in st.session_state:
        st.session_state.csv_path = None
    if 'xlsx_path' not in st.session_state:
        st.session_state.xlsx_path = None
    if 'report_type' not in st.session_state:
        st.session_state.report_type = None
    if 'csv_data' not in st.session_state:
        st.session_state.csv_data = None


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
