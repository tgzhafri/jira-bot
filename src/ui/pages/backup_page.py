import streamlit as st
import logging
from datetime import datetime
from ..components.connection_ui import get_current_config
from ...services.jira_client import JiraClient
from ...services.backup_service import BackupService

logger = logging.getLogger(__name__)

def show():
    """Render the Jira Backup page"""
    st.title("📦 Jira Project Backup")
    st.markdown("Create a full export of your Jira project data including issues, comments, and worklogs.")
    
    config = get_current_config()
    if not config:
        st.warning("⚠️ Please connect to Jira first in the Settings page.")
        if st.button("Go to Settings"):
            st.session_state.current_page = "Settings"
            st.rerun()
        return

    client = JiraClient(config.jira)
    backup_service = BackupService(client)

    # Project Selection & Format
    with st.container(border=True):
        st.subheader("🎯 Target Selection")
        
        # Project Selection with spinner
        with st.spinner("Fetching available projects..."):
            try:
                projects = client.get_all_projects()
                if not projects:
                    st.error("No projects found or unable to fetch projects.")
                    return
            except Exception as e:
                st.error(f"Failed to fetch projects: {e}")
                return

        col1, col2 = st.columns([2, 1])
        with col1:
            selected_project = st.selectbox("Select Project to Backup", projects, help="Choose the Jira project you want to export.")
        
        with col2:
            export_format = st.radio("Export Format", ["ZIP (Compressed JSON)", "JSON (Raw)"], horizontal=False)

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
            include_attachments = st.checkbox("Include Attachment Metadata", value=True, help="Include metadata about attachments (not the files themselves).")

        st.info("ℹ️ Large projects may take several minutes to process.")
        
        if st.button("🏗️ Start Project Backup", type="primary", use_container_width=True):
            status_container = st.empty()
            progress_bar = st.progress(0)
            
            def update_progress(progress, text):
                progress_bar.progress(progress)
                status_container.info(f"⏳ {text}")
                
            try:
                export_data = backup_service.export_project(
                    selected_project,
                    include_comments=include_comments,
                    include_worklogs=include_worklogs,
                    include_attachments_metadata=include_attachments,
                    progress_callback=update_progress
                )
                
                update_progress(0.95, "Packaging backup file...")
                
                if "ZIP" in export_format:
                    file_data = backup_service.create_backup_zip(export_data)
                    mime = "application/zip"
                    ext = "zip"
                else:
                    file_data = backup_service.create_backup_json(export_data).encode('utf-8')
                    mime = "application/json"
                    ext = "json"
                    
                update_progress(1.0, "Backup complete!")
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"jira_backup_{selected_project}_{timestamp}.{ext}"
                
                status_container.success(f"✅ Backup for **{selected_project}** is ready!")
                
                st.download_button(
                    label=f"📥 Download {ext.upper()} Backup",
                    data=file_data,
                    file_name=filename,
                    mime=mime,
                    use_container_width=True,
                    type="primary"
                )
                
            except Exception as e:
                status_container.error(f"❌ Backup failed: {str(e)}")
                logger.exception("Backup failed")
            finally:
                # Progress bar stays until next interaction
                pass

    st.markdown("---")
    
    with st.expander("❓ Backup Details"):
        st.write("""
        - **ZIP Format**: Recommended for large projects. It contains a compressed `project_data.json` file.
        - **JSON Format**: Raw text file, useful for manual inspection or small exports.
        - **Rate Limiting**: This tool respects Jira's API limits by processing issues in batches.
        """)
