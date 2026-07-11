"""FLEX measurement data: writer/storage interfaces.

:class:`DataWriter` is the base class for file formats (HDF5, TDMS, ... via
``flex-datatypes``). Storage backends own where finished files live (local
disk by default; Nextcloud via ``flex-nextcloud``). Writers always write to a
local path — remote backends act only when a file is finalized, so a network
failure can never corrupt a measurement.
"""

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
