"""
Shared backup download UI components.

Provides reusable functions for displaying backup progress, reading
temporary ZIP files into memory, rendering download cards, and
orchestrating the backup-then-download workflow used by both Jira
and Confluence backup pages.
"""

import logging
import os
from datetime import datetime
from typing import Callable, List, Optional, Tuple

import streamlit as st

logger = logging.getLogger(__name__)


def render_download_card(
    file_data: bytes,
    display_name: str,
    prefix: str = "backup",
    key_suffix: Optional[str] = None,
    custom_filename: Optional[str] = None,
) -> None:
    """Render a download card with file info and a download button.

    Args:
        file_data: The ZIP file content in memory.
        display_name: Human-readable name shown in the success message.
        prefix: Filename prefix (e.g., "jira_backup", "confluence_backup").
        key_suffix: Optional suffix for the download button key to avoid
            Streamlit duplicate key errors when rendering multiple cards.
        custom_filename: Optional custom filename for the download. If provided,
            overrides the auto-generated filename from prefix/display_name.
    """
    if custom_filename:
        filename = custom_filename
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "{prefix}_{name}_{ts}.zip".format(
            prefix=prefix, name=display_name, ts=timestamp
        )
    file_size_mb = len(file_data) / (1024 * 1024)

    button_key = "download_{prefix}_{suffix}".format(
        prefix=prefix,
        suffix=key_suffix or display_name,
    )

    with st.container(border=True):
        st.success("✅ Backup complete for **{name}**!".format(name=display_name))
        col_info, col_download = st.columns([2, 1])
        with col_info:
            st.markdown("📁 **{filename}**".format(filename=filename))
            st.caption("Size: {size:.1f} MB".format(size=file_size_mb))
        with col_download:
            st.download_button(
                label="📥 Download ZIP",
                data=file_data,
                file_name=filename,
                mime="application/zip",
                use_container_width=True,
                type="primary",
                key=button_key,
            )


def read_and_cleanup_zip(zip_path: str) -> Optional[bytes]:
    """Read a temporary ZIP file into memory and delete it from disk.

    Args:
        zip_path: Path to the temporary ZIP file.

    Returns:
        File content as bytes, or None if the file doesn't exist.
    """
    if not zip_path or not os.path.exists(zip_path):
        logger.warning("ZIP file not found at: %s", zip_path)
        return None

    with open(zip_path, "rb") as f:
        file_data = f.read()

    os.remove(zip_path)
    return file_data


# Type alias for backup functions that return a temp ZIP path
# Signature: () -> str (path to temp zip)
BackupCallable = Callable[[], Optional[str]]


def run_backup_with_progress(
    backup_fn: BackupCallable,
    display_name: str,
    prefix: str = "backup",
    key_suffix: Optional[str] = None,
) -> None:
    """Run a single backup operation with standard progress UI and download card.

    Orchestrates the common backup workflow:
    1. Show "do not navigate away" warning
    2. Show a progress bar
    3. Execute the backup function
    4. Read the resulting ZIP into memory and clean up
    5. Render the download card

    Args:
        backup_fn: A callable that performs the backup and returns the path
            to a temporary ZIP file, or None on failure. The callable should
            handle its own progress reporting internally.
        display_name: Name shown in the download card (e.g., project key).
        prefix: Filename prefix for the download (e.g., "jira_backup").
        key_suffix: Optional key suffix for the Streamlit download button.
    """
    warning_placeholder = st.empty()
    warning_placeholder.warning(
        "⚠️ **DO NOT refresh or navigate away** while backup is in progress. "
        "This process runs in the background but requires the page to stay "
        "active to complete the download preparation."
    )

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    status_text.text("Starting backup for {}...".format(display_name))

    try:
        progress_bar.progress(0.1)
        status_text.text("Backing up {}...".format(display_name))

        zip_path = backup_fn()

        progress_bar.progress(1.0)
        status_text.empty()
        warning_placeholder.empty()
        progress_bar.empty()

        if not zip_path:
            st.error("❌ Backup failed for **{name}**.".format(name=display_name))
            return

        file_data = read_and_cleanup_zip(zip_path)
        if file_data:
            render_download_card(
                file_data=file_data,
                display_name=display_name,
                prefix=prefix,
                key_suffix=key_suffix,
            )
        else:
            st.error("❌ Backup file could not be read.")

    except Exception as e:
        warning_placeholder.empty()
        progress_bar.empty()
        status_text.empty()
        st.error("❌ Backup failed: {}".format(e))
        logger.exception("Backup failed for %s", display_name)


def run_multi_backup_with_progress(
    backup_items: List[Tuple[str, BackupCallable]],
    prefix: str = "backup",
) -> None:
    """Run multiple backup operations with shared progress UI and download cards.

    Used when backing up multiple items (e.g., multiple Confluence spaces).

    Args:
        backup_items: List of (display_name, backup_callable) tuples.
            Each callable returns a temp ZIP path or None.
        prefix: Filename prefix for downloads.
    """
    warning_placeholder = st.empty()
    warning_placeholder.warning(
        "⚠️ **DO NOT refresh or navigate away** while backup is in progress. "
        "This process runs in the background but requires the page to stay "
        "active to complete the download preparation."
    )

    progress_bar = st.progress(0.0)
    status_text = st.empty()

    results = []  # type: List[Tuple[str, Optional[str], Optional[str]]]
    total = len(backup_items)

    for i, (name, backup_fn) in enumerate(backup_items):
        status_text.text(
            "Backing up {name} ({cur}/{total})...".format(
                name=name, cur=i + 1, total=total
            )
        )
        progress_bar.progress(i / total)

        try:
            zip_path = backup_fn()
            if zip_path:
                results.append((name, zip_path, None))
            else:
                results.append((name, None, "Backup failed (no data found)"))
        except Exception as e:
            results.append((name, None, str(e)))

    progress_bar.progress(1.0)
    status_text.empty()
    warning_placeholder.empty()

    # Display results
    st.markdown("---")
    st.subheader("📋 Results")
    for name, zip_path, error in results:
        if zip_path:
            file_data = read_and_cleanup_zip(zip_path)
            if file_data:
                render_download_card(
                    file_data=file_data,
                    display_name=name,
                    prefix=prefix,
                    key_suffix=name,
                )
            else:
                st.error(
                    "❌ **{name}** — backup file could not be read.".format(
                        name=name
                    )
                )
        else:
            st.error(
                "❌ **{name}** — {err}".format(name=name, err=error)
            )
