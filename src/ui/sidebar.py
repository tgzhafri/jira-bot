import streamlit as st
from datetime import datetime
from typing import Tuple

def render_sidebar() -> Tuple[str, int, int, bool, bool]:
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
