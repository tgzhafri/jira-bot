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
    run_backup_with_progress,
    run_multi_backup_with_progress,
)
from ..components.connection_ui import get_confluence_config
from ...services.confluence_backup_service import ConfluenceBackupService
from ...services.confluence_client import ConfluenceCloudClient

logger = logging.getLogger(__name__)


def _check_connection(client: ConfluenceCloudClient) -> bool:
    """Check if the Confluence instance is reachable, with session-state caching."""
    cache_key = "_confluence_conn_status"
    cache_time_key = "_confluence_conn_check_time"
    ttl_seconds = 60

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


_ALL_SPACES_OPTION = "🌐 ALL SPACES"


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

        # Build dropdown options: "ALL SPACES" + individual spaces
        space_options = [_ALL_SPACES_OPTION] + [
            "{key} — {name}".format(
                key=space.get("key", ""), name=space.get("name", "")
            )
            for space in available_spaces
        ]

        selected_spaces = st.multiselect(
            "Select Spaces",
            options=space_options,
            default=None,
            key="confluence_space_selection",
            help=(
                "Choose one or more spaces to back up. "
                "Select 'ALL SPACES' to back up every available space."
            ),
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
            if _ALL_SPACES_OPTION in selected_spaces:
                space_keys = [
                    space.get("key", "") for space in available_spaces
                ]
            else:
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
        # Single space — use the simpler single-backup flow
        space_key = space_keys[0]

        def do_backup():
            return service.create_zip_backup(
                space_key, include_attachments=include_attachments
            )

        run_backup_with_progress(
            backup_fn=do_backup,
            display_name=space_key,
            prefix="confluence_backup",
            key_suffix=space_key,
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

    # Connection status
    is_reachable = _check_connection(client)
    if is_reachable:
        st.success("✅ Confluence Cloud is reachable")
    else:
        st.warning("⚠️ Cannot reach Confluence Cloud. Check your credentials.")
        return

    st.markdown("---")

    # Backup controls
    _render_space_selector(service)

    # Info section
    _render_info_section()
