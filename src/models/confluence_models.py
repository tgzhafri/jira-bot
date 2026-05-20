"""
Data models for Confluence Cloud backup operations.

Defines dataclasses for representing backed-up pages, attachments,
and space backup metadata.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class BackupAttachment:
    """Represents a backed-up attachment."""

    id: str
    title: str
    file_name: str
    media_type: str
    file_size: int
    download_path: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON export."""
        return {
            "id": self.id,
            "title": self.title,
            "fileName": self.file_name,
            "mediaType": self.media_type,
            "fileSize": self.file_size,
            "downloadPath": self.download_path,
        }

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "BackupAttachment":
        """Parse from Confluence API v2 attachment response.

        The v2 API returns mediaType, fileSize, and downloadLink as
        top-level fields (unlike v1 which nests them under extensions).
        """
        # v2 format: top-level fields
        media_type = data.get(
            "mediaType",
            data.get("extensions", {}).get(
                "mediaType", "application/octet-stream"
            ),
        )
        file_size = data.get(
            "fileSize",
            data.get("extensions", {}).get("fileSize", 0),
        )
        download_path = data.get(
            "downloadLink",
            data.get("_links", {}).get("download", ""),
        )
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            file_name=data.get("title", ""),
            media_type=media_type,
            file_size=file_size,
            download_path=download_path,
        )


@dataclass
class BackupPage:
    """Represents a backed-up Confluence page in storage format."""

    id: str
    title: str
    space_key: str
    storage_body: str  # XHTML storage format — the restorable content
    version_number: int
    parent_id: Optional[str] = None
    ancestors: List[str] = field(default_factory=list)
    attachments: List[BackupAttachment] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON export."""
        return {
            "id": self.id,
            "title": self.title,
            "spaceKey": self.space_key,
            "storageBody": self.storage_body,
            "versionNumber": self.version_number,
            "parentId": self.parent_id,
            "ancestors": self.ancestors,
            "attachments": [a.to_dict() for a in self.attachments],
            "labels": self.labels,
        }

    @classmethod
    def from_api_response(
        cls, data: Dict[str, Any], space_key: str
    ) -> "BackupPage":
        """Parse from Confluence API page response (with body.storage expanded)."""
        body = data.get("body", {}).get("storage", {}).get("value", "")
        version = data.get("version", {}).get("number", 1)
        ancestors = data.get("ancestors", [])
        ancestor_ids = [a["id"] for a in ancestors] if ancestors else []
        parent_id = ancestor_ids[-1] if ancestor_ids else None

        # Labels if expanded
        labels_data = data.get("metadata", {}).get("labels", {}).get("results", [])
        labels = [lbl.get("name", "") for lbl in labels_data]

        return cls(
            id=data["id"],
            title=data.get("title", ""),
            space_key=space_key,
            storage_body=body,
            version_number=version,
            parent_id=parent_id,
            ancestors=ancestor_ids,
            labels=labels,
        )


@dataclass
class SpaceBackupResult:
    """Result of backing up a single Confluence space."""

    space_key: str
    space_name: str
    total_pages: int
    total_attachments: int
    backup_path: str  # Path to the backup directory or ZIP
    timestamp: datetime = field(default_factory=datetime.now)
    errors: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Whether any errors occurred during backup."""
        return len(self.errors) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON metadata."""
        return {
            "spaceKey": self.space_key,
            "spaceName": self.space_name,
            "totalPages": self.total_pages,
            "totalAttachments": self.total_attachments,
            "backupPath": self.backup_path,
            "timestamp": self.timestamp.isoformat(),
            "errors": self.errors,
        }
