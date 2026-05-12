import streamlit as st
from ..components.connection_ui import get_current_config
from ...services.jira_client import JiraClient

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
        client = JiraClient(config.jira)
        with st.spinner("Loading dashboard data..."):
            projects = client.get_all_projects()
            project_count = len(projects) if projects else 0
            
            # This is a bit slow for a dashboard, maybe just show connection info for now
            # or limit to top projects
            
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
    
    c1, c2, c3 = st.columns(3)
    
    with c1:
        with st.container(border=True):
            st.markdown("### 🕒 Manhour Calculator")
            st.write("Generate detailed worklog reports and analyze team capacity.")
            if st.button("Open Calculator", use_container_width=True):
                st.session_state.current_page = "Manhour Calculator"
                st.rerun()
                
    with c2:
        with st.container(border=True):
            st.markdown("### 📦 Jira Backup")
            st.write("Export full project data including issues and comments to JSON/ZIP.")
            if st.button("Open Backup Tool", use_container_width=True):
                st.session_state.current_page = "Jira Backup"
                st.rerun()

    with c3:
        with st.container(border=True):
            st.markdown("### ⚙️ Settings")
            st.write("Manage your Jira credentials and application preferences.")
            if st.button("Open Settings", use_container_width=True):
                st.session_state.current_page = "Settings"
                st.rerun()

    st.markdown("---")
    
    # Recent Activity or Instructions
    with st.expander("📖 How to use this tool", expanded=True):
        st.markdown("""
        1.  **Connect**: Go to **Settings** and enter your Jira URL, Username, and API Token.
        2.  **Dashboard**: Verify your connection and access quick links.
        3.  **Analyze**: Use the **Manhour Calculator** to generate CSV reports of worklogs.
        4.  **Backup**: Use **Jira Backup** to export your data for archival purposes.
        """)
