"""The default data writer: HDF5.

Layout::

    /data/<column>     resizable 1-D datasets, one per column (attr: unit)
    /arrays/<name>     free-form arrays
    attrs              measurement metadata (JSON-encoded snapshot)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from flex.data.writer import ColumnSpec, DataWriter, RowBuffer


class HDF5Writer(DataWriter):
    format_name = "hdf5"
    suffix = ".h5"

    def __init__(self, block_size: int = 1000):
        self._block_size = block_size
        self._file: h5py.File | None = None
        self._buffer: RowBuffer | None = None
        self._row_count = 0

    def open(self, path: Path, *, metadata: dict[str, Any] | None = None) -> None:
        self._file = h5py.File(path, "w")
        self._file.attrs["format"] = "flex"
        if metadata:
            self._file.attrs["metadata"] = json.dumps(metadata, default=str)

    def add_columns(self, columns: list[ColumnSpec]) -> None:
        assert self._file is not None, "open() first"
        group = self._file.require_group("data")
        for col in columns:
            dataset = group.create_dataset(
                col.name, shape=(0,), maxshape=(None,), dtype=col.dtype, chunks=True
            )
            dataset.attrs["unit"] = col.unit
        self._buffer = RowBuffer(columns, block_size=self._block_size)

    def append(self, row: dict[str, Any]) -> None:
        assert self._buffer is not None, "add_columns() first"
        if self._buffer.add(row):
            self._flush()
        self._row_count += 1

    def write_array(self, name: str, data: np.ndarray, *, attrs: dict[str, Any] | None = None) -> None:
        assert self._file is not None, "open() first"
        dataset = self._file.require_group("arrays").create_dataset(name, data=np.asarray(data))
        for key, value in (attrs or {}).items():
            dataset.attrs[key] = value

    def close(self) -> None:
        if self._file is None:
            return
        self._flush()
        self._file.attrs["rows"] = self._row_count
        self._file.close()
        self._file = None

    def _flush(self) -> None:
        if self._buffer is None or self._file is None:
            return
        for name, values in self._buffer.drain().items():
            dataset = self._file["data"][name]
            dataset.resize(dataset.shape[0] + len(values), axis=0)
            dataset[-len(values):] = values
        self._file.flush()
