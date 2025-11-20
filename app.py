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
    
    # Team members count - for quarterly reports, divide by 4 (Q1-Q4 per member)
    team_members = 0
    if not dev_df.empty:
        # Check if this is a quarterly report (columns end with Q1, Q2, Q3, Q4)
        cols = [c for c in dev_df.columns if c not in ['Project', 'Component']]
        if cols and any('Q' in str(col) for col in cols):
            # Quarterly report: each member has 4 columns (Q1-Q4)
            team_members = len(cols) // 4
        else:
            # Yearly report: one column per member
            team_members = len(cols)
    elif not maint_df.empty:
        cols = [c for c in maint_df.columns if c not in ['Project', 'Component']]
        if cols and any('Q' in str(col) for col in cols):
            team_members = len(cols) // 4
        else:
            team_members = len(cols)
    
    return {
        'projects': max(dev_projects, maint_projects),
        'components': dev_components + maint_components,
        'team_members': team_members,
        'dev_hours': dev_hours,
        'maint_hours': maint_hours,
        'total_hours': dev_hours + maint_hours
    }


def transform_to_multiindex(df: pd.DataFrame) -> pd.DataFrame:
    """Transform quarterly columns to multi-level index for better display"""
    if df.empty:
        return df
    
    # Check if this is a quarterly report
    cols = [c for c in df.columns if c not in ['Project', 'Component']]
    if not cols or not any('Q' in str(col) for col in cols):
        return df  # Not quarterly, return as-is
    
    # Create multi-level columns
    new_columns = [('', 'Project'), ('', 'Component')]
    
    for col in cols:
        # Parse "Name Q1" format
        if ' Q' in col:
            parts = col.rsplit(' Q', 1)
            name = parts[0]
            quarter = f'Q{parts[1]}'
            new_columns.append((name, quarter))
        else:
            new_columns.append(('', col))
    
    # Create new dataframe with multi-level columns
    df_multi = df.copy()
    df_multi.columns = pd.MultiIndex.from_tuples(new_columns)
    
    return df_multi


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
            # Transform to multi-level columns for quarterly reports
            dev_display = transform_to_multiindex(dev_df)
            
            # Style the TOTAL row and format numbers to 1 decimal place
            def highlight_total(row):
                # Check if Project column is TOTAL
                if isinstance(dev_display.columns, pd.MultiIndex):
                    is_total = row[('', 'Project')] == 'TOTAL'
                else:
                    is_total = row['Project'] == 'TOTAL'
                return ['background-color: #f0f2f6; font-weight: bold' if is_total else '' for _ in row]
            
            styled_dev = dev_display.style.apply(highlight_total, axis=1)
            
            # Format numeric columns
            if isinstance(dev_display.columns, pd.MultiIndex):
                format_dict = {col: '{:.1f}' for col in dev_display.columns if col not in [('', 'Project'), ('', 'Component')]}
            else:
                format_dict = {col: '{:.1f}' for col in dev_display.columns if col not in ['Project', 'Component']}
                        
            st.dataframe(
                styled_dev,
                use_container_width=True,
                hide_index=True,
                height=300
            )
        
        # Display Maintenance table
        if not maint_df.empty:
            st.markdown("### :hammer_and_wrench: Maintenance")
            # Transform to multi-level columns for quarterly reports
            maint_display = transform_to_multiindex(maint_df)
            
            # Style the TOTAL row and format numbers to 1 decimal place
            def highlight_total(row):
                if isinstance(maint_display.columns, pd.MultiIndex):
                    is_total = row[('', 'Project')] == 'TOTAL'
                else:
                    is_total = row['Project'] == 'TOTAL'
                return ['background-color: #f0f2f6; font-weight: bold' if is_total else '' for _ in row]
            
            styled_maint = maint_display.style.apply(highlight_total, axis=1)
            
            # Format numeric columns
            if isinstance(maint_display.columns, pd.MultiIndex):
                format_dict = {col: '{:.1f}' for col in maint_display.columns if col not in [('', 'Project'), ('', 'Component')]}
            else:
                format_dict = {col: '{:.1f}' for col in maint_display.columns if col not in ['Project', 'Component']}
                        
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
                    result = generate_quarterly_report(
                        config,
                        year=year,
                        output_file=output_file,
                        max_workers=max_workers
                    )
                    # Quarterly returns tuple (csv_path, xlsx_path)
                    csv_path, xlsx_path = result
                    result_path = csv_path
                else:
                    output_file = f"reports/manhour_report_{year}.csv"
                    result_path = generate_csv_report(
                        config,
                        year=year,
                        output_file=output_file,
                        max_workers=max_workers
                    )
                    xlsx_path = None
                
                # Clear progress indicators
                progress_bar.empty()
                progress_text.empty()
                
                if result_path and Path(result_path).exists():
                    # CSV download button
                    with open(result_path, 'rb') as f:
                        csv_data = f.read()
                    
                    # Show download buttons
                    if is_quarterly and xlsx_path and Path(xlsx_path).exists():
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                label=":inbox_tray: Download CSV",
                                data=csv_data,
                                file_name=f"quarterly_report_{year}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        with col2:
                            with open(xlsx_path, 'rb') as f:
                                xlsx_data = f.read()
                            st.download_button(
                                label=":inbox_tray: Download XLSX (Formatted)",
                                data=xlsx_data,
                                file_name=f"quarterly_report_{year}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                    else:
                        st.download_button(
                            label=":inbox_tray: Download CSV Report",
                            data=csv_data,
                            file_name=Path(result_path).name,
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
