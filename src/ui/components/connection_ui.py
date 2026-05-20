import os
from typing import Optional

import streamlit as st
from ...config import Config, AtlassianConfig
from ...services.jira_client import JiraClient, JiraClientError
from ...services.confluence_client import (
    ConfluenceClient,
    ConfluenceClientError,
)


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
    """Render unified Atlassian connection settings form.

    A single set of credentials is used for both Jira and Confluence since they
    share the same Atlassian Cloud authentication.
    """
    st.header("Atlassian Connection Settings")

    with st.form("atlassian_connection_form"):
        st.info(
            "💡 Enter your Atlassian credentials. These are shared across Jira and Confluence. "
            "Credentials are used only for the current session and are not stored anywhere."
        )

        url = st.text_input(
            "Atlassian Instance URL",
            value=st.session_state.atlassian_url,
            placeholder="https://your-domain.atlassian.net",
            help="The base URL of your Atlassian instance (e.g., https://acme.atlassian.net)",
        )

        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input(
                "Username (Email)",
                value=st.session_state.atlassian_username,
                placeholder="your-email@company.com",
                help="Your Atlassian account email address",
            )
        with col2:
            api_token = st.text_input(
                "API Token",
                value=st.session_state.atlassian_api_token,
                type="password",
                placeholder="Atlassian API Token",
                help="Generate at id.atlassian.com/manage-profile/security/api-tokens",
            )

        st.markdown("<br>", unsafe_allow_html=True)
        submit = st.form_submit_button(
            "🚀 Test & Save Connection", use_container_width=True
        )

        if submit:
            # If all empty, clear overrides
            if not any([url, username, api_token]):
                st.session_state.atlassian_url = ""
                st.session_state.atlassian_username = ""
                st.session_state.atlassian_api_token = ""
                st.session_state.atlassian_authenticated = False
                st.session_state.atlassian_connection_error = None
                st.info("Manual overrides cleared. Using environment variables.")
                st.rerun()
            elif not all([url, username, api_token]):
                st.error("Please fill in all fields to override environment variables")
            else:
                try:
                    # Test with Jira first (primary service)
                    temp_config = AtlassianConfig(
                        url=url.strip().rstrip("/"),
                        username=username.strip(),
                        api_token=api_token,
                    )
                    temp_config.validate()

                    client = JiraClient(temp_config, enable_cache=False)

                    with st.spinner("Testing Jira connection..."):
                        if client.test_connection():
                            st.session_state.atlassian_url = url.strip().rstrip("/")
                            st.session_state.atlassian_username = username.strip()
                            st.session_state.atlassian_api_token = api_token
                            st.session_state.atlassian_authenticated = True
                            st.session_state.atlassian_connection_error = None
                            st.success(
                                "✅ Successfully connected to Atlassian!\n\n"
                                f"**URL:** {st.session_state.atlassian_url}\n\n"
                                "These credentials will be used for both Jira and Confluence."
                            )
                            st.rerun()
                        else:
                            st.session_state.atlassian_authenticated = False
                            st.error(
                                "Failed to connect. Please check your credentials."
                            )
                except Exception as e:
                    st.session_state.atlassian_authenticated = False
                    st.session_state.atlassian_connection_error = str(e)
                    st.error(f"Connection error: {str(e)}")


def get_current_config():
    """Get Config object using current session credentials or environment variables"""
    # 1. Try session state (manual override)
    if st.session_state.get("atlassian_authenticated") and st.session_state.atlassian_url:
        atlassian_config = AtlassianConfig(
            url=st.session_state.atlassian_url,
            username=st.session_state.atlassian_username,
            api_token=st.session_state.atlassian_api_token,
        )
        return Config(atlassian=atlassian_config)

    # 2. Try environment variables
    try:
        url = get_secret("ATLASSIAN_URL")
        user = get_secret("ATLASSIAN_USERNAME")
        token = get_secret("ATLASSIAN_API_TOKEN")

        if all([url, user, token]):
            atlassian_config = AtlassianConfig(url=url, username=user, api_token=token)
            atlassian_config.validate()
            return Config(atlassian=atlassian_config)
    except Exception:
        pass

    return None


def display_connection_status():
    """Display connection status indicator with page-aware service check."""
    config = get_current_config()
    if config:
        if st.session_state.get("atlassian_authenticated"):
            st.sidebar.success(f"✅ Connected (Manual): {config.atlassian.url}")
        else:
            st.sidebar.info(f"✅ Connected (Env): {config.atlassian.url}")

        # Show service status based on current page
        current_page = st.session_state.get("current_page", "Dashboard")

        if current_page in ("Manhour Aggregator", "Jira Backup"):
            jira_status = _check_jira_connection(config)
            if jira_status:
                st.sidebar.success("✅ Jira: Connected")
            else:
                st.sidebar.warning("❌ Jira: Disconnected")
        elif current_page == "Confluence Backup":
            confluence_status = _check_confluence_connection(config)
            if confluence_status:
                st.sidebar.success("✅ Confluence Cloud: Connected")
            else:
                st.sidebar.warning("❌ Confluence Cloud: Disconnected")
    else:
        st.sidebar.warning("❌ Not connected to Atlassian")


def _check_jira_connection(config: Config) -> bool:
    """Check Jira connection with session-state caching (60s TTL)."""
    import time

    cache_key = "_jira_conn_status"
    cache_time_key = "_jira_conn_check_time"
    ttl_seconds = 60

    if cache_key in st.session_state:
        last_check = st.session_state.get(cache_time_key, 0)
        if time.time() - last_check < ttl_seconds:
            return st.session_state[cache_key]

    try:
        client = JiraClient(config.atlassian, enable_cache=False)
        result = client.test_connection()
    except Exception:
        result = False

    st.session_state[cache_key] = result
    st.session_state[cache_time_key] = time.time()
    return result


def _check_confluence_connection(config: Config) -> bool:
    """Check Confluence connection with session-state caching (60s TTL)."""
    import time

    cache_key = "_confluence_sidebar_conn_status"
    cache_time_key = "_confluence_sidebar_conn_check_time"
    ttl_seconds = 60

    if cache_key in st.session_state:
        last_check = st.session_state.get(cache_time_key, 0)
        if time.time() - last_check < ttl_seconds:
            return st.session_state[cache_key]

    try:
        confluence_config = get_confluence_config()
        if not confluence_config:
            result = False
        else:
            client = ConfluenceClient(confluence_config)
            result = client.test_connection()
    except Exception:
        result = False

    st.session_state[cache_key] = result
    st.session_state[cache_time_key] = time.time()
    return result


def get_confluence_config() -> Optional[AtlassianConfig]:
    """Get AtlassianConfig from session state or environment variables.

    Uses the same Atlassian credentials since Jira and Confluence share auth.
    Returns AtlassianConfig if valid credentials are available, None otherwise.
    """
    # 1. Try session state (manual override from UI)
    if (
        st.session_state.get("atlassian_authenticated")
        and st.session_state.atlassian_url
    ):
        return AtlassianConfig(
            url=st.session_state.atlassian_url,
            username=st.session_state.atlassian_username,
            api_token=st.session_state.atlassian_api_token,
        )

    # 2. Try environment variables
    try:
        return AtlassianConfig.from_env()
    except (ValueError, Exception):
        pass

    return None
