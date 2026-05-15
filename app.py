#!/usr/bin/env python3
"""
Redesigned Streamlit web UI for Automate Jira
"""

import streamlit as st
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ui.state_manager import initialize_session_state
from src.ui.pages import dashboard_page, worklog_page, jira_backup_page, settings_page, confluence_backup_page
from src.ui.components.connection_ui import display_connection_status
from streamlit_option_menu import option_menu

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Main application entry point"""
    
    # Page config
    st.set_page_config(
        page_title="Atlassian Bot | Automation Tool",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Sidebar Navigation
    with st.sidebar:
        st.title("🤖 Atlassian Bot")
        
        # Define options and icons
        options = ["Dashboard", "Settings", "Manhour Aggregator", "Jira Backup", "Confluence Backup"]
        icons = ["speedometer2", "gear", "clock-history", "archive", "cloud-download"]

        # Determine default index from session state (set by Quick Action buttons)
        default_idx = 0
        if "current_page" in st.session_state and st.session_state.current_page in options:
            default_idx = options.index(st.session_state.current_page)

        selected = option_menu(
            menu_title=None,
            options=options,
            icons=icons,
            menu_icon="robot",
            default_index=default_idx,
            key="nav_menu",
            styles={
                "container": {"padding": "5!important", "background-color": "transparent"},
                "icon": {"font-size": "1.2rem"},
                "nav-link": {"font-size": "1rem", "text-align": "left", "margin": "0px", "--hover-color": "#f4f5f7", "color": "#0052cc"},
                "nav-link-selected": {"background-color": "#0052cc", "color": "white"},
            }
        )
        
        st.session_state.current_page = selected
        
        st.markdown("---")
        # Display connection status in sidebar
        display_connection_status()
        
        st.markdown("---")
        st.caption("v1.2.0 | Built with ❤️")

    # Routing
    if selected == "Settings":
        settings_page.show()
    elif selected == "Dashboard":
        dashboard_page.show()
    elif selected == "Manhour Aggregator":
        worklog_page.show()
    elif selected == "Jira Backup":
        jira_backup_page.show()
    elif selected == "Confluence Backup":
        confluence_backup_page.show()

    # Global Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.8em;'>
        Atlassian Bot | Supports Jira & Confluence Cloud REST API
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
