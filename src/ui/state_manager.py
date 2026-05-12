import streamlit as st

def initialize_session_state():
    """Initialize session state variables"""
    if 'report_generated' not in st.session_state:
        st.session_state.report_generated = False
    if 'csv_path' not in st.session_state:
        st.session_state.csv_path = None
    if 'xlsx_path' not in st.session_state:
        st.session_state.xlsx_path = None
    if 'report_type' not in st.session_state or st.session_state.report_type is None:
        st.session_state.report_type = "Yearly Overview"
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Settings"
    if 'csv_data' not in st.session_state:
        st.session_state.csv_data = None
        
    # Jira Credentials
    if 'jira_url' not in st.session_state:
        st.session_state.jira_url = ""
    if 'jira_username' not in st.session_state:
        st.session_state.jira_username = ""
    if 'jira_api_token' not in st.session_state:
        st.session_state.jira_api_token = ""
    if 'jira_authenticated' not in st.session_state:
        st.session_state.jira_authenticated = False
    if 'jira_connection_error' not in st.session_state:
        st.session_state.jira_connection_error = None
