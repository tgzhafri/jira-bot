"""
Confluence Cloud Backup page.

Backs up Confluence spaces via the REST API in storage format (XHTML)
with attachments. Provides page-by-page progress reporting.
"""

import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from typing import List
from urllib.parse import urlparse

import streamlit as st

from ..components.backup_download import (
    read_and_cleanup_zip,
    render_download_card,
)
from ..components.connection_ui import get_confluence_config
from ...services.confluence_backup_service import ConfluenceBackupService
from ...services.confluence_client import ConfluenceClient

logger = logging.getLogger(__name__)


def _get_instance_name(config) -> str:
    """Extract instance name from the Atlassian URL."""
    try:
        hostname = urlparse(config.url).hostname or ""
        parts = hostname.split(".")
        if parts:
            return parts[0]
    except Exception:
        pass
    return "confluence"


def _make_backup_filename(config, space_key=None) -> str:
    """Build a download filename like inscaleasia_confluence_backup_2026_05_19.zip."""
    instance = _get_instance_name(config)
    date_str = datetime.now().strftime("%Y_%m_%d")
    if space_key:
        return "{}_confluence_backup_{}_{}.zip".format(instance, space_key, date_str)
    return "{}_confluence_backup_{}.zip".format(instance, date_str)


def _fetch_available_spaces(service):
    """Fetch available spaces with session-state caching (5 min TTL)."""
    cache_key = "_confluence_spaces_list"
    cache_time_key = "_confluence_spaces_fetch_time"

    if cache_key in st.session_state:
        if time.time() - st.session_state.get(cache_time_key, 0) < 300:
            return st.session_state[cache_key]

    try:
        spaces = service.list_spaces()
        st.session_state[cache_key] = spaces
        st.session_state[cache_time_key] = time.time()
        return spaces
    except Exception as e:
        logger.error("Failed to fetch spaces: %s", e)
        return []


# ---------------------------------------------------------------------------
# Backup execution
# ---------------------------------------------------------------------------


def _run_backup(config, service, space_keys, include_attachments):
    """Run backup for selected spaces with page-by-page progress."""
    warning_placeholder = st.empty()
    warning_placeholder.warning(
        "⚠️ **DO NOT refresh or navigate away** while backup is in progress."
    )

    progress_bar = st.progress(0.0)
    status_text = st.empty()

    if len(space_keys) == 1:
        _run_single_space(
            config, service, space_keys[0], include_attachments,
            warning_placeholder, progress_bar, status_text,
        )
    else:
        _run_multiple_spaces(
            config, service, space_keys, include_attachments,
            warning_placeholder, progress_bar, status_text,
        )


def _run_single_space(
    config, service, space_key, include_attachments,
    warning_placeholder, progress_bar, status_text,
):
    """Back up a single space with detailed page-by-page progress."""
    status_text.text("[{}] Starting backup...".format(space_key))

    def progress_callback(message, current, total):
        if total > 0:
            progress_bar.progress(min(current / total, 0.95))
            status_text.text("[{key}] {msg} ({cur}/{total})".format(
                key=space_key, msg=message, cur=current, total=total
            ))
        else:
            status_text.text("[{}] {}".format(space_key, message))

    try:
        zip_path = service.create_zip_backup(
            space_key,
            include_attachments=include_attachments,
            progress_callback=progress_callback,
        )

        progress_bar.progress(1.0)
        status_text.empty()
        warning_placeholder.empty()
        progress_bar.empty()

        if not zip_path:
            st.error("❌ Backup failed for **{}**.".format(space_key))
            return

        file_data = read_and_cleanup_zip(zip_path)
        if file_data:
            render_download_card(
                file_data=file_data,
                display_name=space_key,
                prefix="confluence_backup",
                key_suffix=space_key,
                custom_filename=_make_backup_filename(config, space_key=space_key),
            )
        else:
            st.error("❌ Backup file could not be read.")

    except Exception as e:
        warning_placeholder.empty()
        progress_bar.empty()
        status_text.empty()
        st.error("❌ Backup failed: {}".format(e))
        logger.exception("Backup failed for %s", space_key)


def _run_multiple_spaces(
    config, service, space_keys, include_attachments,
    warning_placeholder, progress_bar, status_text,
):
    """Back up multiple spaces into a single combined ZIP with directories."""
    total_spaces = len(space_keys)
    all_results = []
    errors = []

    for i, space_key in enumerate(space_keys):
        space_base_pct = i / total_spaces
        space_pct_range = 1.0 / total_spaces

        def progress_callback(
            message, current, total,
            _base=space_base_pct, _range=space_pct_range, _key=space_key, _i=i,
        ):
            if total > 0:
                overall_pct = min(_base + (_range * current / total), 0.95)
                progress_bar.progress(overall_pct)
                status_text.text(
                    "[{key}] {msg} ({cur}/{tot}) — space {si}/{st}".format(
                        key=_key, msg=message, cur=current, tot=total,
                        si=_i + 1, st=total_spaces,
                    )
                )
            else:
                progress_bar.progress(min(_base + 0.01, 0.95))
                status_text.text("[{key}] {msg} — space {si}/{st}".format(
                    key=_key, msg=message, si=_i + 1, st=total_spaces,
                ))

        status_text.text("[{key}] Starting... — space {si}/{st}".format(
            key=space_key, si=i + 1, st=total_spaces,
        ))
        progress_bar.progress(min(space_base_pct, 0.95))

        try:
            result = service.backup_space(
                space_key,
                include_attachments=include_attachments,
                progress_callback=progress_callback,
            )
            all_results.append(result)
        except Exception as e:
            errors.append("Space {}: {}".format(space_key, e))
            logger.exception("Backup failed for %s", space_key)

    # Combine into a single ZIP
    status_text.text("Creating combined ZIP archive...")
    progress_bar.progress(0.96)

    fd, combined_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    try:
        with zipfile.ZipFile(combined_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for result in all_results:
                if not os.path.exists(result.backup_path):
                    continue
                for root, dirs, files in os.walk(result.backup_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join(
                            result.space_key,
                            os.path.relpath(file_path, result.backup_path),
                        )
                        zf.write(file_path, arcname)

            metadata = {
                "timestamp": datetime.now().isoformat(),
                "spaces_exported": [r.space_key for r in all_results],
                "total_pages": sum(r.total_pages for r in all_results),
                "total_attachments": sum(r.total_attachments for r in all_results),
                "include_attachments": include_attachments,
                "errors": errors,
            }
            zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    finally:
        for result in all_results:
            shutil.rmtree(result.backup_path, ignore_errors=True)

    progress_bar.progress(1.0)
    status_text.empty()
    warning_placeholder.empty()
    progress_bar.empty()

    file_data = read_and_cleanup_zip(combined_path)
    if file_data:
        total_pages = sum(r.total_pages for r in all_results)
        total_attachments = sum(r.total_attachments for r in all_results)
        st.success(
            "✅ Backup complete — {} spaces, {} pages, {} attachments".format(
                len(all_results), total_pages, total_attachments,
            )
        )
        if errors:
            with st.expander("⚠️ Errors ({})".format(len(errors))):
                for err in errors:
                    st.text(err)
        render_download_card(
            file_data=file_data,
            display_name=_get_instance_name(config),
            prefix="confluence_backup",
            key_suffix="combined",
            custom_filename=_make_backup_filename(config),
        )
    else:
        st.error("❌ Backup file could not be read.")


# ---------------------------------------------------------------------------
# Main Page
# ---------------------------------------------------------------------------


def show() -> None:
    """Render the Confluence Backup page."""
    st.title("📦 Confluence Backup")
    st.markdown(
        "Create a full export of your Confluence spaces including pages "
        "and attachments in storage format (XHTML)."
    )

    config = get_confluence_config()
    if not config:
        st.warning("⚠️ Please connect to Confluence first in the Settings page.")
        if st.button("Go to Settings"):
            st.session_state.current_page = "Settings"
            st.rerun()
        return

    client = ConfluenceClient(config)
    service = ConfluenceBackupService(client)

    # --- Target Selection ---
    with st.container(border=True):
        st.subheader("🎯 Target Selection")

        with st.spinner("Fetching available spaces..."):
            available_spaces = _fetch_available_spaces(service)

        if not available_spaces:
            st.error("No spaces found or unable to fetch spaces.")
            return

        space_options = [
            "{key} — {name}".format(
                key=space.get("key", ""), name=space.get("name", "")
            )
            for space in available_spaces
        ]

        selected_spaces = st.multiselect(
            "Select Spaces",
            options=space_options,
            default=space_options,
            key="backup_space_selection",
            help="Choose which spaces to back up. All spaces selected by default.",
        )

    st.markdown("---")

    # --- Backup Options ---
    with st.container(border=True):
        st.subheader("🛠️ Backup Options")

        include_attachments = st.checkbox(
            "Include Attachments (Files)",
            value=True,
            help=(
                "Download and include file attachments from pages. "
                "May significantly increase backup time and size."
            ),
        )

        if selected_spaces and len(selected_spaces) == len(space_options):
            st.warning(
                "⚠️ **Note**: You are about to backup **{}** spaces. "
                "This may take a significant amount of time depending on "
                "total pages and attachments.".format(len(available_spaces))
            )

        st.info(
            "ℹ️ Large spaces may take several minutes to process. "
            "Parallel processing is enabled for page downloads."
        )

        if st.button(
            "🏗️ Start Backup",
            type="primary",
            use_container_width=True,
        ):
            if not selected_spaces:
                st.error("Please select at least one space.")
                return

            space_keys = [
                option.split(" — ")[0].strip()
                for option in selected_spaces
            ]
            space_keys = [k for k in space_keys if k]

            if not space_keys:
                st.error("No valid space keys resolved.")
                return

            _run_backup(config, service, space_keys, include_attachments)

    st.markdown("---")

    # --- Details ---
    with st.expander("❓ Backup Details", expanded=True):
        st.write(
            """
- **Storage Format**: Pages are exported in Confluence storage format (XHTML) as JSON files with metadata.
- **Attachments**: Binary files stored alongside pages, organized by page ID.
- **Structure**: Single space exports produce a flat ZIP. Multi-space exports group files by space directory.
- **Performance**: Uses parallel API calls (multi-threading) for page processing and attachment downloads.
- **Permissions**: Requires read access to the spaces being backed up.
        """
        )
