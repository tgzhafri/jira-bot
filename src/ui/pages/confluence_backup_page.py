"""
Confluence Cloud Backup page.

Provides UI controls for backing up Confluence Cloud spaces by exporting
pages in storage format (restorable XHTML) along with attachments.
"""

import logging
import time
from typing import List

import streamlit as st

from ..components.backup_download import (
    run_multi_backup_with_progress,
)
from ..components.connection_ui import get_confluence_config
from ...services.confluence_backup_service import ConfluenceBackupService
from ...services.confluence_client import ConfluenceCloudClient

logger = logging.getLogger(__name__)


def _fetch_available_spaces(service: ConfluenceBackupService) -> list:
    """Fetch available spaces with session-state caching.

    Returns:
        List of space dicts with key and name fields.
    """
    cache_key = "_confluence_spaces_list"
    cache_time_key = "_confluence_spaces_fetch_time"
    ttl_seconds = 300  # Cache for 5 minutes

    if cache_key in st.session_state:
        last_fetch = st.session_state.get(cache_time_key, 0)
        if time.time() - last_fetch < ttl_seconds:
            return st.session_state[cache_key]

    try:
        spaces = service.list_spaces()
        st.session_state[cache_key] = spaces
        st.session_state[cache_time_key] = time.time()
        return spaces
    except Exception as e:
        logger.error("Failed to fetch spaces: %s", e)
        return []


def _render_space_selector(service: ConfluenceBackupService) -> None:
    """Render space selection and backup controls."""
    with st.container(border=True):
        st.subheader("📂 Space Backup")
        st.caption(
            "Export pages in **storage format** (native XHTML) — "
            "this is the format Confluence uses internally and can be "
            "restored via the REST API."
        )

        available_spaces = _fetch_available_spaces(service)

        if not available_spaces:
            st.warning(
                "⚠️ Could not retrieve spaces from Confluence. "
                "Check your permissions or try again."
            )
            return

        # Build dropdown options from individual spaces
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
            key="confluence_space_selection",
            help="Choose one or more spaces to back up.",
        )

        # Options
        include_attachments = st.toggle(
            "Include Attachments",
            value=True,
            key="confluence_include_attachments",
            help="Download all file attachments from pages.",
        )

        # Backup button
        if st.button(
            "🏗️ Start Backup", type="primary", key="start_confluence_backup"
        ):
            if not selected_spaces:
                st.error("Please select at least one space.")
                return

            # Resolve selected space keys
            space_keys = [
                option.split(" — ")[0].strip()
                for option in selected_spaces
            ]

            space_keys = [k for k in space_keys if k]
            if not space_keys:
                st.error("No valid space keys resolved.")
                return

            _run_backup(service, space_keys, include_attachments)


def _run_backup(
    service: ConfluenceBackupService,
    space_keys: List[str],
    include_attachments: bool,
) -> None:
    """Execute the backup using shared progress/download infrastructure."""
    if len(space_keys) == 1:
        # Single space — use progress-aware flow with detailed status
        space_key = space_keys[0]
        _run_single_backup_with_detailed_progress(
            service, space_key, include_attachments
        )
    else:
        # Multiple spaces — use multi-backup flow with per-item cards
        backup_items = [
            (
                space_key,
                lambda sk=space_key: service.create_zip_backup(
                    sk, include_attachments=include_attachments
                ),
            )
            for space_key in space_keys
        ]
        run_multi_backup_with_progress(
            backup_items=backup_items,
            prefix="confluence_backup",
        )


def _run_single_backup_with_detailed_progress(
    service: ConfluenceBackupService,
    space_key: str,
    include_attachments: bool,
) -> None:
    """Run a single-space backup with detailed progress reporting.

    Shows page names, counts, and attachment status in the progress bar.
    """
    from ..components.backup_download import (
        read_and_cleanup_zip,
        render_download_card,
    )

    warning_placeholder = st.empty()
    warning_placeholder.warning(
        "⚠️ **DO NOT refresh or navigate away** while backup is in progress. "
        "This process runs in the background but requires the page to stay "
        "active to complete the download preparation."
    )

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    status_text.text("[{}] Starting backup...".format(space_key))

    def progress_callback(message, current, total):
        """Update Streamlit progress bar from backup service."""
        if total > 0:
            pct = min(current / total, 0.95)
            progress_bar.progress(pct)
            status_text.text(
                "[{key}] {msg} ({cur}/{total})".format(
                    key=space_key, msg=message, cur=current, total=total
                )
            )
        else:
            # Indeterminate phase (fetching pages, creating ZIP)
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
            st.error(
                "❌ Backup failed for **{name}**.".format(name=space_key)
            )
            return

        file_data = read_and_cleanup_zip(zip_path)
        if file_data:
            render_download_card(
                file_data=file_data,
                display_name=space_key,
                prefix="confluence_backup",
                key_suffix=space_key,
            )
        else:
            st.error("❌ Backup file could not be read.")

    except Exception as e:
        warning_placeholder.empty()
        progress_bar.empty()
        status_text.empty()
        st.error("❌ Backup failed: {}".format(e))
        logger.exception("Backup failed for %s", space_key)


def _render_info_section() -> None:
    """Render information about the backup format."""
    with st.expander("ℹ️ About this backup format", expanded=True):
        st.markdown(
            """
**Storage Format (XHTML)** is the native internal representation Confluence
uses for page content. It preserves:

- All formatting, macros, and structured content
- Page hierarchy (parent/child relationships)
- Labels and metadata

**To restore** a page from backup, use the Confluence REST API:

```python
confluence.create_page(
    space=space_key,
    title=page_title,
    body=storage_body,  # from the backup JSON
    representation="storage"
)
```

**Attachments** are saved as raw files alongside page metadata and can be
re-uploaded via the API.
"""
        )


def show() -> None:
    """Render the Confluence Backup page."""
    st.title("📦 Confluence Backup")
    st.markdown(
        "Back up Confluence Cloud spaces in **storage format** "
        "(restorable via REST API)."
    )

    # Check configuration
    config = get_confluence_config()
    if not config:
        st.warning(
            "⚠️ Confluence is not configured. "
            "Please set up your connection in the Settings page."
        )
        if st.button("Go to Settings"):
            st.session_state.current_page = "Settings"
            st.rerun()
        return

    # Initialize client and service
    client = ConfluenceCloudClient(config)
    service = ConfluenceBackupService(client)

    st.markdown("---")

    # Backup controls
    _render_space_selector(service)

    # Info section
    _render_info_section()
