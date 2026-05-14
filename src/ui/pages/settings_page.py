import streamlit as st
from ..components.connection_ui import render_connection_settings, display_connection_status
from ... import __version__


def show():
    """Render the Settings page"""
    st.title("⚙️ Settings")
    st.markdown("Configure your Atlassian connection and application preferences.")

    # Unified Atlassian Connection Settings
    with st.container(border=True):
        render_connection_settings()

    st.markdown("---")

    # App Info Section
    with st.container(border=True):
        st.subheader("📱 Application Information")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Version:** {__version__}")
            st.write("**Build Type:** Stable")
            st.write("**Architecture:** Modular Service-Oriented")

        with col2:
            st.write(f"**Framework:** Streamlit {st.__version__}")
            st.write("**API Support:** Jira & Confluence Cloud REST API")

    st.markdown("---")
    st.info(
        "💡 **Tip:** Credentials are stored in your browser session and are cleared "
        "when you refresh the page or close the tab. The same credentials are used "
        "for both Jira and Confluence."
    )
