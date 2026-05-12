import streamlit as st
from pathlib import Path
import logging
from datetime import datetime
from ..components.connection_ui import get_current_config
from ...services.worklog_service import (
    generate_csv_report,
    generate_quarterly_report,
    generate_monthly_breakdown_report,
    generate_weekly_breakdown_report
)
from ..report_view import display_stored_report

logger = logging.getLogger(__name__)

def generate_report_by_type(config, report_type: str, year: int, max_workers: int):
    """Generate report based on selected type"""
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
    if report_type == "Yearly Overview":
        return (result, None) if result else None
    else:
        return result if result else None

def handle_report_generation(config, report_type: str, year: int, max_workers: int):
    """Handle report generation with progress indicators"""
    progress_container = st.empty()
    with progress_container.container():
        st.info(f"⏳ Generating {report_type} report for {year}...")
        progress_bar = st.progress(0)
        
        try:
            # Simulate initial progress
            progress_bar.progress(10)
            result = generate_report_by_type(config, report_type, year, max_workers)
            progress_bar.progress(100)
            
            if result:
                csv_path, xlsx_path = result
                if csv_path and Path(csv_path).exists():
                    st.session_state.report_generated = True
                    st.session_state.csv_path = csv_path
                    st.session_state.xlsx_path = xlsx_path
                    st.session_state.report_type = report_type
                    
                    with open(csv_path, 'rb') as f:
                        st.session_state.csv_data = f.read()
                    st.success("✅ Report generated successfully!")
                else:
                    st.warning("⚠️ No data found for the specified period.")
            else:
                st.warning("⚠️ No data found for the specified period.")
        except Exception as e:
            st.error(f"❌ Error generating report: {e}")
            logger.exception("Report generation failed")
        finally:
            # Short delay then clear progress info
            import time
            time.sleep(1)
            progress_container.empty()

def show():
    """Render the Manhour Calculator page"""
    st.title("🕒 Manhour Calculator")
    st.markdown("Generate and analyze Jira worklog reports to track team capacity and project hours.")
    
    config = get_current_config()
    if not config:
        st.warning("⚠️ Please connect to Jira first in the Settings page.")
        if st.button("Go to Settings"):
            st.session_state.current_page = "Settings"
            st.rerun()
        return

    # Configuration Section
    with st.container(border=True):
        st.subheader("📋 Report Configuration")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            report_options = ["Yearly Overview", "Quarterly Breakdown", "Monthly Breakdown", "Weekly Breakdown"]
            current_report_type = st.session_state.get('report_type') or "Yearly Overview"
            if current_report_type not in report_options:
                current_report_type = "Yearly Overview"
                
            report_type = st.selectbox(
                "Report Type",
                report_options,
                index=report_options.index(current_report_type)
            )
        
        with col2:
            current_year = datetime.now().year
            year = st.number_input("Year", min_value=2020, max_value=current_year, value=current_year)
            
        with col3:
            max_workers = st.slider("Parallel Workers", 1, 20, 8, help="Higher values speed up generation but may hit Jira rate limits.")

        st.markdown("---")
        
        action_col1, action_col2 = st.columns([3, 1])
        with action_col1:
            if st.button("🚀 Generate Report", type="primary", use_container_width=True):
                handle_report_generation(config, report_type, year, max_workers)
        
        with action_col2:
            if st.button("🗑️ Clear Cache", use_container_width=True):
                cache_path = Path(config.jira.cache_dir)
                if cache_path.exists():
                    import shutil
                    shutil.rmtree(cache_path)
                    st.success("Cache cleared!")
                    st.rerun()

    st.markdown("---")
    
    # Results Section
    if st.session_state.get('report_generated') and st.session_state.get('report_type') == report_type:
        st.subheader("📊 Report Results")
        display_stored_report()
