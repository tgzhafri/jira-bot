import os
import streamlit as st
from ...config import Config, JiraConfig
from ...services.jira_client import JiraClient, JiraClientError

def get_secret(key, default=""):
    """Safely get secret from streamlit secrets or environment variables"""
    try:
        # Check streamlit secrets first
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # st.secrets might raise an error if not configured at all
        pass
    return os.getenv(key, default)

def render_connection_settings():
    """Render Jira connection settings in a sidebar or main area"""
    st.header("Jira Connection Settings")
    
    with st.form("jira_connection_form"):
        st.info("💡 Enter your Jira credentials to use this feature. Credentials are used only for the current session and are not stored anywhere.")
        
        url = st.text_input(
            "Jira Instance URL", 
            value=st.session_state.jira_url,
            placeholder="https://your-domain.atlassian.net",
            help="The base URL of your Jira instance (e.g., https://acme.atlassian.net)"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input(
                "Jira Username", 
                value=st.session_state.jira_username,
                placeholder="your-email@company.com",
                help="Your Atlassian account email address"
            )
        with col2:
            api_token = st.text_input(
                "API Token", 
                value=st.session_state.jira_api_token,
                type="password",
                placeholder="Atlassian API Token",
                help="Generate this at id.atlassian.com/manage-profile/security/api-tokens"
            )
        
        st.markdown("<br>", unsafe_allow_html=True)
        submit = st.form_submit_button("🚀 Test & Save Connection", use_container_width=True)
        
        if submit:
            # If all empty, clear overrides
            if not any([url, username, api_token]):
                st.session_state.jira_url = ""
                st.session_state.jira_username = ""
                st.session_state.jira_api_token = ""
                st.session_state.jira_authenticated = False
                st.info("Manual overrides cleared. Using environment variables.")
                st.rerun()
            elif not all([url, username, api_token]):
                st.error("Please fill in all fields to override environment variables")
            else:
                try:
                    # Create temporary config for testing
                    temp_config = JiraConfig(
                        url=url.rstrip('/'),
                        username=username,
                        api_token=api_token
                    )
                    temp_config.validate()
                    
                    client = JiraClient(temp_config, enable_cache=False)
                    
                    with st.spinner("Testing connection..."):
                        if client.test_connection():
                            st.session_state.jira_url = url
                            st.session_state.jira_username = username
                            st.session_state.jira_api_token = api_token
                            st.session_state.jira_authenticated = True
                            st.session_state.jira_connection_error = None
                            st.success("Successfully connected with provided credentials!")
                            st.rerun()
                        else:
                            st.session_state.jira_authenticated = False
                            st.error("Failed to connect to Jira. Please check your credentials.")
                except Exception as e:
                    st.session_state.jira_authenticated = False
                    st.error(f"Connection error: {str(e)}")

def get_current_config():
    """Get Config object using current session credentials or environment variables"""
    # 1. Try session state (manual override)
    if st.session_state.get('jira_authenticated') and st.session_state.jira_url:
        jira_config = JiraConfig(
            url=st.session_state.jira_url,
            username=st.session_state.jira_username,
            api_token=st.session_state.jira_api_token
        )
        return Config(jira=jira_config)
    
    # 2. Try environment variables
    try:
        url = get_secret("JIRA_URL")
        user = get_secret("JIRA_USERNAME")
        token = get_secret("JIRA_API_TOKEN")
        
        if all([url, user, token]):
            jira_config = JiraConfig(url=url, username=user, api_token=token)
            jira_config.validate()
            return Config(jira=jira_config)
    except Exception:
        pass
        
    return None

def display_connection_status():
    """Display connection status indicator"""
    config = get_current_config()
    if config:
        if st.session_state.get('jira_authenticated'):
            st.sidebar.success(f"✅ Connected (Manual): {config.jira.url}")
        else:
            st.sidebar.info(f"✅ Connected (Env): {config.jira.url}")
    else:
        st.sidebar.warning("❌ Not connected to Jira")

