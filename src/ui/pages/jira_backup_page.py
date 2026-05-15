"""
Jira Project Backup page.

Provides UI controls for creating full exports of Jira project data
including issues, comments, worklogs, and attachments as ZIP archives.
"""

import logging

import streamlit as st

from ..components.backup_download import run_backup_with_progress
from ..components.connection_ui import get_current_config
from ...services.jira_backup_service import JiraBackupService
from ...services.jira_client import JiraClient

logger = logging.getLogger(__name__)


def show():
    """Render the Jira Backup page."""
    st.title("📦 Jira Project Backup")
    st.markdown(
        "Create a full export of your Jira project data including issues, "
        "comments, worklogs, and attachments."
    )

    config = get_current_config()
    if not config:
        st.warning("⚠️ Please connect to Jira first in the Settings page.")
        if st.button("Go to Settings"):
            st.session_state.current_page = "Settings"
            st.rerun()
        return

    client = JiraClient(config.atlassian)
    backup_service = JiraBackupService(client)

    # Project Selection & Format
    with st.container(border=True):
        st.subheader("🎯 Target Selection")

        with st.spinner("Fetching available projects..."):
            try:
                available_projects = client.get_all_projects()
                if not available_projects:
                    st.error("No projects found or unable to fetch projects.")
                    return

                project_options = ["ALL PROJECTS"] + available_projects

            except Exception as e:
                st.error("Failed to fetch projects: {}".format(e))
                return

        col1, col2 = st.columns([2, 1])
        with col1:
            selected_project = st.selectbox(
                "Select Project to Backup",
                project_options,
                help="Choose a specific project or backup everything at once.",
            )
        with col2:
            st.selectbox(
                "Export Format",
                ["ZIP Archive (Optimized)"],
                disabled=True,
            )

    st.markdown("---")

    # Backup Options
    with st.container(border=True):
        st.subheader("🛠️ Backup Options")

        c1, c2, c3 = st.columns(3)
        with c1:
            include_comments = st.checkbox(
                "Include Comments",
                value=True,
                help="Include all issue comments in the export.",
            )
        with c2:
            include_worklogs = st.checkbox(
                "Include Worklogs",
                value=True,
                help="Include all worklog entries.",
            )
        with c3:
            include_attachments = st.checkbox(
                "Include Attachments (Files)",
                value=True,
                help=(
                    "Download and include actual attachment files. "
                    "May significantly increase backup time and size."
                ),
            )

        if selected_project == "ALL PROJECTS":
            st.warning(
                "⚠️ **Note**: You are about to backup **{}** projects. "
                "This may take a significant amount of time depending on "
                "total issues and attachments.".format(len(available_projects))
            )

        st.info(
            "ℹ️ Large projects may take several minutes to process. "
            "Parallel processing is enabled."
        )

        if st.button(
            "🏗️ Start Project Backup",
            type="primary",
            use_container_width=True,
        ):
            # Resolve target
            if selected_project == "ALL PROJECTS":
                target_projects = available_projects
                display_name = "ALL_PROJECTS"
            else:
                target_projects = selected_project
                display_name = selected_project

            def do_backup():
                return backup_service.export_project(
                    target_projects,
                    include_comments=include_comments,
                    include_worklogs=include_worklogs,
                    include_attachments=include_attachments,
                )

            run_backup_with_progress(
                backup_fn=do_backup,
                display_name=display_name,
                prefix="jira_backup",
            )

    st.markdown("---")

    with st.expander("❓ Backup Details", expanded=True):
        st.write(
            """
        - **ZIP Archive (Optimized)**: Now includes a structured export:
            - **Single Project**: Files located at root of ZIP.
            - **Bulk Backup**: Files grouped by project folder (e.g., `PROJ/project.json`).
            - `metadata.json`: Export summary and settings.
            - `attachments/`: Folder containing actual files organized by issue key.
        - **Performance**: We use parallel API calls (multi-threading) and incremental ZIP writing to optimize speed and memory usage.
        - **Rate Limiting**: This tool respects Jira's API limits by processing issues in batches.
        """
        )
