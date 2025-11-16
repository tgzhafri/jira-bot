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
from scripts.generate_report import generate_csv_report

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# UI Components
# ============================================================================

def show_config_error(error_msg: str):
    """Display configuration error with helpful instructions"""
    st.error("⚠️ Missing Configuration")
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


def calculate_summary_stats(df: pd.DataFrame) -> dict:
    """Calculate summary statistics from the report DataFrame"""
    # Filter out TOTAL row and empty rows for accurate counts
    data_df = df[df['Project'].notna() & (df['Project'] != 'TOTAL')]
    
    unique_projects = data_df['Project'].nunique() if 'Project' in data_df.columns else 0
    unique_components = data_df['Component'].nunique() if 'Component' in data_df.columns else 0
    team_members = len(df.columns) - 2
    
    # Get total hours from the TOTAL row if it exists
    total_row = df[df['Project'] == 'TOTAL']
    if not total_row.empty:
        numeric_cols = total_row.select_dtypes(include=['float64', 'int64']).columns
        total_hours = total_row[numeric_cols].sum().sum()
    else:
        numeric_cols = data_df.select_dtypes(include=['float64', 'int64']).columns
        total_hours = data_df[numeric_cols].sum().sum()
    
    return {
        'total_rows': len(data_df),
        'projects': unique_projects,
        'components': unique_components,
        'team_members': team_members,
        'total_hours': total_hours
    }


def display_report_preview(result_path: Path, csv_data: bytes):
    """Display report preview with table and summary statistics"""
    st.subheader("📄 Report Preview")
    
    try:
        df = pd.read_csv(result_path)
        stats = calculate_summary_stats(df)
        
        # Display summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Projects", stats['projects'])
        with col2:
            st.metric("Components", stats['components'])
        with col3:
            st.metric("Team Members", stats['team_members'])
        with col4:
            st.metric("Total Hours", f"{stats['total_hours']:.1f}h")
        
        # Display table
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=400
        )
        
    except Exception as e:
        st.warning(f"Could not display preview: {e}")
        with st.expander("📄 Raw CSV Preview"):
            st.code(csv_data.decode('utf-8')[:1000] + "\n...", language="csv")





# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main application entry point"""
    
    # Page config
    st.set_page_config(
        page_title="Automate Jira",
        page_icon="📊",
        layout="wide"
    )
    
    # Header
    st.title("📊 Automate Jira")
    st.markdown("Generate CSV reports of team hours by project and component")
    
    # Sidebar configuration
    st.sidebar.header("⚙️ Configuration")
    
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
        
        # Cache management
        if st.button("🗑️ Clear Cache", help="Delete all cached API responses"):
            cache_path = Path(".cache")
            if cache_path.exists():
                import shutil
                shutil.rmtree(cache_path)
                cache_path.mkdir(exist_ok=True)
                st.success("✅ Cache cleared!")
                st.rerun()
            else:
                st.info("Cache is already empty")
    
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
        
        # Show connection info
        st.success(f"✅ Connected to: {config.jira.url}")
        if config.jira.project_keys:
            st.info(f"📁 Projects: {', '.join(config.jira.project_keys)}")
        else:
            st.info("📁 Projects: All accessible projects")
        
        # Show cache status
        if config.jira.enable_cache:
            cache_path = Path(config.jira.cache_dir)
            cache_files = list(cache_path.glob("*.json")) if cache_path.exists() else []
            if cache_files:
                st.info(f"💾 Cache: Enabled ({len(cache_files)} cached responses in {cache_path})")
            else:
                st.info(f"💾 Cache: Enabled (empty - will populate on first run at {cache_path})")
        else:
            st.warning("💾 Cache: Disabled")
        
    except ValueError as e:
        show_config_error(str(e))
    except Exception as e:
        st.error(f"❌ Configuration error: {e}")
        st.stop()
    
    # Generate button
    if st.button("🚀 Generate Report", type="primary", use_container_width=True):
        with st.spinner(f"Generating team overview report for {year}..."):
            try:
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                Path("reports").mkdir(exist_ok=True)
                
                progress_text.text("Fetching data from Jira...")
                progress_bar.progress(30)
                
                # Generate team overview report
                output_file = f"reports/manhour_report_{year}.csv"
                download_filename = f"manhour_report_{year}.csv"
                
                result_path = generate_csv_report(
                    config,
                    year=year,
                    output_file=output_file,
                    max_workers=max_workers
                )
                
                progress_bar.progress(100)
                progress_text.empty()
                
                if result_path and Path(result_path).exists():
                    st.success("✅ Report generated successfully!")
                    
                    with open(result_path, 'rb') as f:
                        csv_data = f.read()
                    
                    st.download_button(
                        label="📥 Download CSV Report",
                        data=csv_data,
                        file_name=download_filename,
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    display_report_preview(Path(result_path), csv_data)
                else:
                    st.warning("⚠️ No data found for the specified period")
                    
            except Exception as e:
                st.error(f"❌ Error generating report: {e}")
                logger.exception("Report generation failed")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        Built with ❤️ using Streamlit | Automate Jira v1.0.0
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
