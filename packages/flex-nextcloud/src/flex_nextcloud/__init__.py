"""FLEX storage backend for Nextcloud (WebDAV)."""

from flex_nextcloud.storage import NextcloudStorage

__version__ = "2.0.0a1"

#: Storage backend name -> "module:Class" reference.
STORAGE: dict[str, str] = {"nextcloud": "flex_nextcloud.storage:NextcloudStorage"}

__all__ = ["STORAGE", "NextcloudStorage"]
