import streamlit as st
from ..components.connection_ui import get_current_config
from ...services.jira_client import JiraClient


def _get_project_count(config) -> int:
    """Fetch project count with session-state caching to avoid repeated API calls."""
    cache_key = "_dashboard_project_count"
    cache_url_key = "_dashboard_project_url"

    # Return cached value if the connection URL hasn't changed
    if (
        cache_key in st.session_state
        and st.session_state.get(cache_url_key) == config.jira.url
    ):
        return st.session_state[cache_key]

    client = JiraClient(config.jira)
    projects = client.get_all_projects()
    count = len(projects) if projects else 0

    st.session_state[cache_key] = count
    st.session_state[cache_url_key] = config.jira.url
    return count


def show():
    """Render the Dashboard page"""
    st.title("📊 Project Dashboard")
    st.markdown("Welcome to your Jira Automation command center.")

    config = get_current_config()

    if not config:
        st.warning("⚠️ Jira connection not configured. Please go to **Settings** to connect.")
        st.info("Once connected, you'll see project metrics and quick actions here.")
        return

    # Connection Status Banner
    st.success(f"✅ Connected to **{config.jira.url}** as **{config.jira.username}**")

    # Quick Metrics
    col1, col2, col3, col4 = st.columns(4)

    try:
        with st.spinner("Loading dashboard data..."):
            project_count = _get_project_count(config)

        with col1:
            st.metric("Projects Accessible", project_count)
        with col2:
            st.metric("Connection Type", "Cloud API v3")
        with col3:
            st.metric("Authenticated", "Yes")
        with col4:
            st.metric("Environment", "Production")

    except Exception as e:
        st.error(f"Error fetching dashboard data: {e}")

    st.markdown("---")

    # Feature Cards
    st.subheader("Quick Actions")

    # Scoped CSS — only targets the quick-actions container
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"].quick-actions-row
            > div[data-testid="stColumn"]
            > div[data-testid="stVerticalBlockBorderWrapper"] {
            height: 200px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        with st.container(border=True):
            st.subheader("🕒 Manhour Calculator")
            st.caption(
                "Generate detailed worklog reports and analyze team capacity."
            )
            if st.button("Open Calculator", use_container_width=True):
                st.session_state.current_page = "Manhour Calculator"
                if "nav_menu" in st.session_state:
                    del st.session_state["nav_menu"]
                st.rerun()

    with c2:
        with st.container(border=True):
            st.subheader("📦 Jira Backup")
            st.caption(
                "Export full project data including issues and comments to JSON/ZIP."
            )
            if st.button("Open Backup Tool", use_container_width=True):
                st.session_state.current_page = "Jira Backup"
                if "nav_menu" in st.session_state:
                    del st.session_state["nav_menu"]
                st.rerun()

    with c3:
        with st.container(border=True):
            st.subheader("⚙️ Settings")
            st.caption(
                "Manage your Atlassian credentials and application preferences."
            )
            if st.button("Open Settings", use_container_width=True):
                st.session_state.current_page = "Settings"
                if "nav_menu" in st.session_state:
                    del st.session_state["nav_menu"]
                st.rerun()

    st.markdown("---")

    # Recent Activity or Instructions
    with st.expander("📖 How to use this tool", expanded=True):
        st.markdown("""
        1.  **Connect**: Go to **Settings** and enter your Atlassian URL, Username, and API Token.
        2.  **Dashboard**: Verify your connection and access quick links.
        3.  **Analyze**: Use the **Manhour Calculator** to generate CSV reports of worklogs.
        4.  **Backup**: Use **Jira Backup** to export your data for archival purposes.
        5.  **Confluence**: Use **Confluence Backup** to create site or space backups.
        """)
