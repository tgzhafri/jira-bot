import streamlit as st
from ..components.connection_ui import render_connection_settings, display_connection_status

def show():
    """Render the Settings page"""
    st.title("⚙️ Settings")
    st.markdown("Configure your Jira connection and application preferences.")
    
    # Use a container for grouped settings
    with st.container(border=True):
        render_connection_settings()
    
    st.markdown("---")
    
    # App Info Section
    with st.container(border=True):
        st.subheader("📱 Application Information")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Version:** 1.2.0")
            st.write("**Build Type:** Stable")
            st.write("**Architecture:** Modular Service-Oriented")
        
        with col2:
            st.write("**Framework:** Streamlit 1.57.0")
            st.write("**API Support:** Jira Cloud REST API v3")

    st.markdown("---")
    st.info("💡 **Tip:** Credentials are stored in your browser session and are cleared when you refresh the page or close the tab.")
