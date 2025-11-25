import streamlit as st
from pathlib import Path
from . import display_report_preview

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
