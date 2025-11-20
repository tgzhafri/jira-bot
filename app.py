#!/usr/bin/env python3
"""
Streamlit web UI for Automate Jira
"""

import streamlit as st
import sys
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.jira_client import JiraClient
from src.utils import get_month_range, format_date_for_jql
from src.report_generator import generate_csv_report, generate_quarterly_report

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# UI Components
# ============================================================================

def show_config_error(error_msg: str):
    """Display configuration error with helpful instructions"""
    st.error(":warning: Missing Configuration")
    st.markdown("""
    Please set these environment variables:
    ```
    JIRA_URL=https://your-company.atlassian.net
    JIRA_USERNAME=your-email@company.com
    JIRA_API_TOKEN=your-api-token
    ```
    
    **For Docker:** Make sure your `.env` file exists and restart:
    ```bash
    make web-stop
    make web
    ```
    """)
    st.error(f"Error details: {error_msg}")
    st.stop()


def parse_split_csv(file_path: Path) -> tuple:
    """Parse CSV file split by Development and Maintenance sections"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    dev_lines = []
    maint_lines = []
    current_section = None
    
    for line in lines:
        stripped = line.strip()
        if stripped == 'DEVELOPMENT':
            current_section = 'dev'
            continue
        elif stripped == 'MAINTENANCE':
            current_section = 'maint'
            continue
        elif not stripped:
            continue
        
        if current_section == 'dev':
            dev_lines.append(line)
        elif current_section == 'maint':
            maint_lines.append(line)
    
    # Parse into DataFrames
    from io import StringIO
    dev_df = pd.read_csv(StringIO(''.join(dev_lines))) if dev_lines else pd.DataFrame()
    maint_df = pd.read_csv(StringIO(''.join(maint_lines))) if maint_lines else pd.DataFrame()
    
    return dev_df, maint_df


def calculate_summary_stats(dev_df: pd.DataFrame, maint_df: pd.DataFrame) -> dict:
    """Calculate summary statistics from both Development and Maintenance DataFrames"""
    
    def get_stats_from_df(df):
        if df.empty:
            return 0, 0, 0
        data_df = df[df['Project'].notna() & (df['Project'] != 'TOTAL')]
        projects = data_df['Project'].nunique() if 'Project' in data_df.columns else 0
        components = data_df['Component'].nunique() if 'Component' in data_df.columns else 0
        
        # Get total hours from TOTAL row
        total_row = df[df['Project'] == 'TOTAL']
        if not total_row.empty:
            numeric_cols = total_row.select_dtypes(include=['float64', 'int64']).columns
            hours = total_row[numeric_cols].sum().sum()
        else:
            numeric_cols = data_df.select_dtypes(include=['float64', 'int64']).columns
            hours = data_df[numeric_cols].sum().sum()
        
        return projects, components, hours
    
    dev_projects, dev_components, dev_hours = get_stats_from_df(dev_df)
    maint_projects, maint_components, maint_hours = get_stats_from_df(maint_df)
    
    # Team members count (from either df, should be same)
    team_members = 0
    if not dev_df.empty:
        team_members = len(dev_df.columns) - 2
    elif not maint_df.empty:
        team_members = len(maint_df.columns) - 2
    
    return {
        'projects': max(dev_projects, maint_projects),
        'components': dev_components + maint_components,
        'team_members': team_members,
        'dev_hours': dev_hours,
        'maint_hours': maint_hours,
        'total_hours': dev_hours + maint_hours
    }


def display_report_preview(result_path: Path, csv_data: bytes):
    """Display report preview with separate tables for Development and Maintenance"""
    st.subheader(":clipboard: Report Preview")
    
    try:
        # Parse the split CSV
        dev_df, maint_df = parse_split_csv(result_path)
        stats = calculate_summary_stats(dev_df, maint_df)
        
        # Display summary metrics in two rows
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Projects", stats['projects'])
        with col2:
            st.metric("Components", stats['components'])
        with col3:
            st.metric("Team Members", stats['team_members'])
        
        # Display hours breakdown in one row
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Development Hours", f"{stats['dev_hours']:.1f}h")
        with col2:
            st.metric("Maintenance Hours", f"{stats['maint_hours']:.1f}h")
        with col3:
            st.metric("Total Hours", f"{stats['total_hours']:.1f}h")
        
        # Display Development table
        if not dev_df.empty:
            st.markdown("### :wrench: Development")
            # Style the TOTAL row and format numbers to 1 decimal place
            styled_dev = dev_df.style.apply(
                lambda x: ['background-color: #f0f2f6; font-weight: bold' if x['Project'] == 'TOTAL' else '' for _ in x],
                axis=1
            ).format({col: '{:.1f}' for col in dev_df.columns if col not in ['Project', 'Component']}, na_rep='')
            st.dataframe(
                styled_dev,
                use_container_width=True,
                hide_index=True,
                height=300
            )
        
        # Display Maintenance table
        if not maint_df.empty:
            st.markdown("### :hammer_and_wrench: Maintenance")
            # Style the TOTAL row and format numbers to 1 decimal place
            styled_maint = maint_df.style.apply(
                lambda x: ['background-color: #f0f2f6; font-weight: bold' if x['Project'] == 'TOTAL' else '' for _ in x],
                axis=1
            ).format({col: '{:.1f}' for col in maint_df.columns if col not in ['Project', 'Component']}, na_rep='')
            st.dataframe(
                styled_maint,
                use_container_width=True,
                hide_index=True,
                height=300
            )
        
    except Exception as e:
        st.warning(f"Could not display preview: {e}")
        logger.exception("Preview display failed")
        with st.expander(":page_facing_up: Raw CSV Preview"):
            st.code(csv_data.decode('utf-8')[:1000] + "\n...", language="csv")





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
    
    # Sidebar configuration
    st.sidebar.header(":gear: Configuration")
    
    # Report type selector
    report_type = st.sidebar.radio(
        "Report Type",
        options=["Yearly Overview", "Quarterly Breakdown"],
        index=0,
        help="Choose between yearly summary or quarterly breakdown"
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
        
        # Cache management - will be handled after config is loaded
        clear_cache_clicked = st.button(":wastebasket: Clear Cache", help="Delete all cached API responses")
    
    st.markdown("---")
    
    # Load and validate configuration
    try:
        config = Config.from_env()
        config.jira.enable_cache = use_cache
        config.jira.max_workers = max_workers
        
        # Ensure cache directory is absolute path
        if not Path(config.jira.cache_dir).is_absolute():
            config.jira.cache_dir = str(Path.cwd() / config.jira.cache_dir)
        
        config.validate()
        
        # Show connection info in compact format
        cache_path = Path(config.jira.cache_dir)
        cache_files = list(cache_path.glob("*.json")) if cache_path.exists() else []
        
        if config.jira.enable_cache and cache_files:
            cache_status = f"{len(cache_files)} cached"
        elif not config.jira.enable_cache:
            cache_status = "disabled"
        else:
            cache_status = "empty"
        
        # Display connection info
        st.info(f":link: Connected: {config.jira.url} | :floppy_disk: Cache: {cache_status}")
        
        # Handle cache clearing after config is loaded
        if clear_cache_clicked:
            if cache_path.exists() and cache_path.is_dir():
                import shutil
                # Clear contents without removing directory
                for item in cache_path.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                st.success(":white_check_mark: Cache cleared!")
                st.rerun()
            else:
                st.info("Cache directory does not exist")
        
    except ValueError as e:
        show_config_error(str(e))
        return
    except Exception as e:
        st.error(f":x: Configuration error: {e}")
        st.stop()
        return
    
    # Generate button
    button_label = ":rocket: Generate Report"
    if st.button(button_label, type="primary", use_container_width=True):
        # Determine report type and settings
        is_quarterly = report_type == "Quarterly Breakdown"
        report_name = "quarterly breakdown" if is_quarterly else "yearly overview"
        
        with st.spinner(f"Generating {report_name} report for {year}..."):
            try:
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                Path("reports").mkdir(exist_ok=True)
                
                progress_text.text("Fetching data from Jira...")
                progress_bar.progress(30)
                
                # Generate report based on type
                if is_quarterly:
                    output_file = f"reports/quarterly_report_{year}.csv"
                    download_filename = f"quarterly_report_{year}.csv"
                    result_path = generate_quarterly_report(
                        config,
                        year=year,
                        output_file=output_file,
                        max_workers=max_workers
                    )
                else:
                    output_file = f"reports/manhour_report_{year}.csv"
                    download_filename = f"manhour_report_{year}.csv"
                    result_path = generate_csv_report(
                        config,
                        year=year,
                        output_file=output_file,
                        max_workers=max_workers
                    )
                
                # Clear progress indicators
                progress_bar.empty()
                progress_text.empty()
                
                if result_path and Path(result_path).exists():
                    with open(result_path, 'rb') as f:
                        csv_data = f.read()
                    
                    st.download_button(
                        label=":inbox_tray: Download CSV Report",
                        data=csv_data,
                        file_name=download_filename,
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    display_report_preview(Path(result_path), csv_data)
                else:
                    st.warning(":warning: No data found for the specified period")
                    
            except Exception as e:
                st.error(f":x: Error generating report: {e}")
                logger.exception("Report generation failed")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        Built using Streamlit | Automate Jira v1.0.0
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
