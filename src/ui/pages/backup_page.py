import streamlit as st
import logging
import os
from datetime import datetime
from ..components.connection_ui import get_current_config
from ...services.jira_client import JiraClient
from ...services.backup_service import BackupService

logger = logging.getLogger(__name__)

def show():
    """Render the Jira Backup page"""
    st.title("📦 Jira Project Backup")
    st.markdown("Create a full export of your Jira project data including issues, comments, worklogs, and attachments.")
    
    config = get_current_config()
    if not config:
        st.warning("⚠️ Please connect to Jira first in the Settings page.")
        if st.button("Go to Settings"):
            st.session_state.current_page = "Settings"
            st.rerun()
        return

    client = JiraClient(config.atlassian)
    backup_service = BackupService(client)

    # Project Selection & Format
    with st.container(border=True):
        st.subheader("🎯 Target Selection")
        
        # Project Selection with spinner
        with st.spinner("Fetching available projects..."):
            try:
                available_projects = client.get_all_projects()
                if not available_projects:
                    st.error("No projects found or unable to fetch projects.")
                    return
                
                project_options = ["ALL PROJECTS"] + available_projects
                
            except Exception as e:
                st.error(f"Failed to fetch projects: {e}")
                return

        col1, col2 = st.columns([2, 1])
        with col1:
            selected_project = st.selectbox(
                "Select Project to Backup", 
                project_options, 
                help="Choose a specific project or backup everything at once."
            )
        
        with col2:
            # We've optimized ZIP, so it's the preferred and now only recommended format for full backups
            export_format = st.selectbox("Export Format", ["ZIP Archive (Optimized)"], disabled=True)

    st.markdown("---")

    # Backup Options
    with st.container(border=True):
        st.subheader("🛠️ Backup Options")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            include_comments = st.checkbox("Include Comments", value=True, help="Include all issue comments in the export.")
        with c2:
            include_worklogs = st.checkbox("Include Worklogs", value=True, help="Include all worklog entries.")
        with c3:
            include_attachments = st.checkbox("Include Attachments (Files)", value=True, help="Download and include actual attachment files. May significantly increase backup time and size.")

        if selected_project == "ALL PROJECTS":
            st.warning(f"⚠️ **Note**: You are about to backup **{len(available_projects)}** projects. This may take a significant amount of time depending on total issues and attachments.")

        st.info("ℹ️ Large projects may take several minutes to process. Parallel processing is enabled.")
        
        if st.button("🏗️ Start Project Backup", type="primary", use_container_width=True):
            # Persistent warning
            warning_placeholder = st.empty()
            warning_placeholder.warning("⚠️ **DO NOT refresh or navigate away** while backup is in progress. This process runs in the background but requires the page to stay active to complete the download preparation.")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Decide which project(s) to backup
            if selected_project == "ALL PROJECTS":
                target_projects = available_projects
                display_name = "ALL_PROJECTS"
            else:
                target_projects = selected_project
                display_name = selected_project

            def update_progress(progress, text):
                progress_bar.progress(progress)
                status_text.info(f"⏳ Processing: {text}")
                
            try:
                # Run the backup
                temp_zip_path = backup_service.export_project(
                    target_projects,
                    include_comments=include_comments,
                    include_worklogs=include_worklogs,
                    include_attachments=include_attachments,
                    progress_callback=update_progress
                )
                
                progress_bar.progress(1.0)
                status_text.empty()
                
                # Read the file for download
                with open(temp_zip_path, "rb") as f:
                    file_data = f.read()
                
                # Clean up temp file
                os.remove(temp_zip_path)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"jira_backup_{display_name}_{timestamp}.zip"
                file_size_mb = len(file_data) / (1024 * 1024)
                
                # Remove the warning after success
                warning_placeholder.empty()
                
                # Show download card
                with st.container(border=True):
                    st.success(f"✅ Backup complete for **{display_name}**!")
                    col_info, col_download = st.columns([2, 1])
                    with col_info:
                        st.markdown(f"📁 **{filename}**")
                        st.caption(f"Size: {file_size_mb:.1f} MB")
                    with col_download:
                        st.download_button(
                            label="📥 Download ZIP",
                            data=file_data,
                            file_name=filename,
                            mime="application/zip",
                            use_container_width=True,
                            type="primary"
                        )
                
            except Exception as e:
                status_text.empty()
                st.error(f"❌ Backup failed: {str(e)}")
                logger.exception("Backup failed")

    st.markdown("---")
    
    with st.expander("❓ Backup Details", expanded=True):
        st.write("""
        - **ZIP Archive (Optimized)**: Now includes a structured export:
            - **Single Project**: Files located at root of ZIP.
            - **Bulk Backup**: Files grouped by project folder (e.g., `PROJ/project.json`).
            - `metadata.json`: Export summary and settings.
            - `attachments/`: Folder containing actual files organized by issue key.
        - **Performance**: We use parallel API calls (multi-threading) and incremental ZIP writing to optimize speed and memory usage.
        - **Rate Limiting**: This tool respects Jira's API limits by processing issues in batches.
        """)
