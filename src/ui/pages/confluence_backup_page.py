"""
Confluence Data Center Backup page.

Provides UI controls for creating site/space backups, monitoring job progress,
downloading completed backups, viewing job history, and cancelling active jobs.
"""

import logging
import time
from typing import Optional

import pandas as pd
import streamlit as st

from ...config import AtlassianConfig
from ...models.confluence_models import ConfluenceJobDetails, ConfluenceJobState
from ...services.confluence_backup_service import ConfluenceBackupService
from ...services.confluence_client import ConfluenceClient, ConfluenceClientError

logger = logging.getLogger(__name__)


def _get_confluence_config() -> Optional[AtlassianConfig]:
    """Get Atlassian configuration from session state or environment variables.

    Returns:
        AtlassianConfig if configured, None otherwise.
    """
    # Try session state first (UI-driven configuration)
    if st.session_state.get("atlassian_authenticated") and st.session_state.get("atlassian_url"):
        try:
            config = AtlassianConfig(
                url=st.session_state["atlassian_url"],
                username=st.session_state["atlassian_username"],
                api_token=st.session_state["atlassian_api_token"],
            )
            config.validate()
            return config
        except (ValueError, KeyError):
            pass

    # Try environment variables
    try:
        return AtlassianConfig.from_env()
    except (ValueError, KeyError):
        pass

    return None


def _check_connection(client: ConfluenceClient) -> bool:
    """Check if the Confluence instance is reachable, with session-state caching."""
    cache_key = "_confluence_conn_status"
    cache_time_key = "_confluence_conn_check_time"
    ttl_seconds = 60

    # Return cached result if still fresh
    if cache_key in st.session_state:
        last_check = st.session_state.get(cache_time_key, 0)
        if time.time() - last_check < ttl_seconds:
            return st.session_state[cache_key]

    try:
        result = client.test_connection()
    except Exception:
        result = False

    st.session_state[cache_key] = result
    st.session_state[cache_time_key] = time.time()
    return result


def _render_connection_status(is_reachable: bool) -> None:
    """Display connection status indicator."""
    if is_reachable:
        st.success("✅ Confluence instance is reachable")
    else:
        st.warning("⚠️ Confluence instance is unreachable")


def _render_site_backup_controls(service: ConfluenceBackupService) -> None:
    """Render site backup creation controls."""
    with st.container(border=True):
        st.subheader("🌐 Site Backup")
        st.caption("Create a full backup of the entire Confluence instance.")

        col1, col2 = st.columns(2)
        with col1:
            skip_attachments = st.toggle(
                "Skip Attachments",
                value=False,
                key="site_skip_attachments",
                help="Exclude attachments from the backup to reduce size.",
            )
        with col2:
            keep_permanently = st.toggle(
                "Keep Permanently",
                value=False,
                key="site_keep_permanently",
                help="Retain the backup file indefinitely on the server.",
            )

        file_name_prefix = st.text_input(
            "File Name Prefix (optional)",
            value="",
            max_chars=100,
            key="site_file_name_prefix",
            help="Custom prefix for the backup filename (max 200 chars). Alphanumeric, hyphens, and underscores only.",
        )

        if st.button("🏗️ Start Site Backup", type="primary", key="start_site_backup"):
            prefix = file_name_prefix.strip() if file_name_prefix.strip() else None
            try:
                job = service.create_site_backup(
                    skip_attachments=skip_attachments,
                    keep_permanently=keep_permanently,
                    file_name_prefix=prefix,
                )
                st.session_state["confluence_active_job"] = job
                st.success(f"Site backup job created: {job.id}")
                st.rerun()
            except (ConfluenceClientError, ValueError) as e:
                st.error(f"Failed to create site backup: {e}")


def _render_space_backup_controls(service: ConfluenceBackupService) -> None:
    """Render space backup creation controls."""
    with st.container(border=True):
        st.subheader("📂 Space Backup")
        st.caption("Create a backup of specific Confluence spaces.")

        space_keys_input = st.text_input(
            "Space Keys",
            value="",
            key="space_keys_input",
            help="Comma-separated list of space keys to back up (e.g., DEV, HR, DOCS).",
            placeholder="DEV, HR, DOCS",
        )

        col1, col2 = st.columns(2)
        with col1:
            keep_permanently = st.toggle(
                "Keep Permanently",
                value=False,
                key="space_keep_permanently",
                help="Retain the backup file indefinitely on the server.",
            )
        with col2:
            file_name_prefix = st.text_input(
                "File Name Prefix (optional)",
                value="",
                max_chars=100,
                key="space_file_name_prefix",
                help="Custom prefix (max 100 chars). Alphanumeric, hyphens, and underscores only.",
            )

        if st.button("🏗️ Start Space Backup", type="primary", key="start_space_backup"):
            # Parse space keys
            raw_keys = [k.strip() for k in space_keys_input.split(",") if k.strip()]
            if not raw_keys:
                st.error("Please enter at least one space key.")
                return

            prefix = file_name_prefix.strip() if file_name_prefix.strip() else None
            try:
                job = service.create_space_backup(
                    space_keys=raw_keys,
                    keep_permanently=keep_permanently,
                    file_name_prefix=prefix,
                )
                st.session_state["confluence_active_job"] = job
                st.success(f"Space backup job created: {job.id}")
                st.rerun()
            except (ConfluenceClientError, ValueError) as e:
                st.error(f"Failed to create space backup: {e}")


def _render_active_job_progress(service: ConfluenceBackupService) -> None:
    """Display progress indicator for the active job."""
    job: Optional[ConfluenceJobDetails] = st.session_state.get("confluence_active_job")
    if job is None:
        return

    # Refresh job status
    try:
        job = service.get_job_status(job.id)
        st.session_state["confluence_active_job"] = job
    except ConfluenceClientError as e:
        st.error(f"Failed to fetch job status: {e}")
        return

    with st.container(border=True):
        st.subheader("⏳ Active Job")

        # State indicator
        state_label = job.job_state.value
        scope_label = job.job_scope.value

        if job.job_state == ConfluenceJobState.QUEUED:
            st.info(f"**State:** {state_label} | **Scope:** {scope_label}")
        elif job.job_state == ConfluenceJobState.IN_PROGRESS:
            st.info(f"**State:** {state_label} | **Scope:** {scope_label}")
            # Progress bar
            if job.statistics and job.statistics.total_objects_count > 0:
                progress = job.statistics.processed_objects_count / job.statistics.total_objects_count
                st.progress(
                    min(progress, 1.0),
                    text=f"Processing: {job.statistics.processed_objects_count} / {job.statistics.total_objects_count} objects",
                )
            else:
                st.progress(0.0, text="Processing...")
        elif job.job_state == ConfluenceJobState.COMPLETED:
            st.success(f"✅ Job completed! | **Scope:** {scope_label}")
            if job.file_name:
                st.info(f"📁 File: {job.file_name}")
                # Download the backup file
                try:
                    import tempfile
                    from pathlib import Path

                    dest = Path(tempfile.mkdtemp()) / job.file_name
                    with st.spinner("Downloading backup file from server..."):
                        service.download_backup(job.id, dest)

                    with open(dest, "rb") as f:
                        file_data = f.read()

                    file_size_mb = len(file_data) / (1024 * 1024)
                    st.caption(f"Size: {file_size_mb:.1f} MB")

                    st.download_button(
                        label="📥 Download Backup",
                        data=file_data,
                        file_name=job.file_name,
                        mime="application/zip",
                        use_container_width=True,
                        type="primary",
                        key="download_backup",
                    )

                    # Clean up temp file after offering download
                    dest.unlink(missing_ok=True)
                except ConfluenceClientError as e:
                    st.error(f"Failed to download backup: {e}")

            # Clear active job
            if st.button("Clear", key="clear_active_job"):
                st.session_state["confluence_active_job"] = None
                st.rerun()
        elif job.job_state == ConfluenceJobState.FAILED:
            error_msg = job.error_message or "Unknown error"
            st.error(f"❌ Job failed: {error_msg}")
            if st.button("Clear", key="clear_failed_job"):
                st.session_state["confluence_active_job"] = None
                st.rerun()
        elif job.job_state == ConfluenceJobState.CANCELLED:
            st.warning(f"🚫 Job was cancelled by {job.cancelled_by or 'unknown'}")
            if st.button("Clear", key="clear_cancelled_job"):
                st.session_state["confluence_active_job"] = None
                st.rerun()

        # Cancel button for non-terminal jobs
        if job.job_state in (ConfluenceJobState.QUEUED, ConfluenceJobState.IN_PROGRESS):
            if st.button("🛑 Cancel Job", key="cancel_active_job"):
                try:
                    service.cancel_job(job.id)
                    st.warning("Job cancellation requested.")
                    st.rerun()
                except ConfluenceClientError as e:
                    st.error(f"Failed to cancel job: {e}")

            # Auto-refresh for in-progress jobs (poll every 5 seconds)
            time.sleep(5)
            st.rerun()


def _render_job_history(service: ConfluenceBackupService) -> None:
    """Display job history table with the 20 most recent jobs."""
    with st.container(border=True):
        st.subheader("📋 Job History")

        try:
            jobs = service.list_jobs(limit=20)
        except ConfluenceClientError as e:
            st.error(f"Failed to fetch job history: {e}")
            return

        if not jobs:
            st.info("No backup or restore jobs found.")
            return

        # Build table data
        rows = []
        for job in jobs:
            rows.append({
                "Status": job.job_state.value,
                "Scope": job.job_scope.value,
                "Operation": job.job_operation.value,
                "Created": job.create_time.strftime("%Y-%m-%d %H:%M") if job.create_time else "—",
                "Filename": job.file_name or "—",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Cancel buttons for active jobs
        active_jobs = [
            j for j in jobs
            if j.job_state in (ConfluenceJobState.QUEUED, ConfluenceJobState.IN_PROGRESS)
        ]
        if active_jobs:
            st.markdown("**Active Jobs:**")
            for job in active_jobs:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text(f"{job.id} ({job.job_state.value} - {job.job_scope.value})")
                with col2:
                    if st.button("🛑 Cancel", key=f"cancel_{job.id}"):
                        try:
                            service.cancel_job(job.id)
                            st.success(f"Cancelled job {job.id}")
                            st.rerun()
                        except ConfluenceClientError as e:
                            st.error(f"Failed to cancel: {e}")


def show() -> None:
    """Render the Confluence Backup page."""
    st.title("📦 Confluence Backup")
    st.markdown("Create and manage backups of your Confluence Data Center instance.")

    # Check configuration
    config = _get_confluence_config()
    if not config:
        st.warning("⚠️ Confluence is not configured. Please set up your connection in the Settings page.")
        if st.button("Go to Settings"):
            st.session_state.current_page = "Settings"
            st.rerun()
        return

    # Initialize client and service
    client = ConfluenceClient(config)
    service = ConfluenceBackupService(client)

    # Connection status
    is_reachable = _check_connection(client)
    _render_connection_status(is_reachable)

    st.markdown("---")

    # Active job progress (if any)
    if st.session_state.get("confluence_active_job"):
        _render_active_job_progress(service)
        st.markdown("---")

    # Backup controls
    col_site, col_space = st.columns(2)
    with col_site:
        _render_site_backup_controls(service)
    with col_space:
        _render_space_backup_controls(service)

    st.markdown("---")

    # Job history
    _render_job_history(service)
