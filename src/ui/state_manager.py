import streamlit as st

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
