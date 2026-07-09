"""FLEX measurement data: writers and storage backends.

Writers own the file format (HDF5 by default; TDMS via ``flex-tdms``).
Storage backends own where finished files live (local disk by default;
Nextcloud via ``flex-nextcloud``). Writers always write to a local path —
remote backends act only when a file is finalized, so a network failure can
never corrupt a measurement.
"""

from flex.data.hdf5 import HDF5Writer
from flex.data.storage import FilePointer, LocalStorage, StorageBackend
from flex.data.writer import ColumnSpec, DataWriter

__all__ = [
    "ColumnSpec",
    "DataWriter",
    "FilePointer",
    "HDF5Writer",
    "LocalStorage",
    "StorageBackend",
]
