"""Data writer and storage interfaces. Writers always write locally; remote storage acts only
in ``finalize``, so a network failure can't corrupt a measurement."""

from flex.data.storage import FilePointer, LocalStorage, StorageBackend
from flex.data.writer import ColumnSpec, DataWriter

#: Storage backend name -> "module:Class" reference.
STORAGE: dict[str, str] = {"local": "flex.data.storage:LocalStorage"}

__all__ = [
    "STORAGE",
    "ColumnSpec",
    "DataWriter",
    "FilePointer",
    "LocalStorage",
    "StorageBackend",
]
