"""TDMS writer, laid out for the lab's LabVIEW/DataViewer tools: columns are channels in
``Data.000000`` (with a ``unit`` property), arrays are channels in ``Arrays``, metadata
is root properties."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from nptdms import ChannelObject, RootObject, TdmsWriter

from flex.data.writer import ColumnSpec, DataWriter, RowBuffer

_DATA_GROUP = "Data.000000"
_ARRAY_GROUP = "Arrays"


class TDMSWriter(DataWriter):
    suffix = ".tdms"

    def __init__(self, block_size: int = 1000):
        self._block_size = block_size
        self._writer: TdmsWriter | None = None
        self._buffer: RowBuffer | None = None
        self._units: dict[str, str] = {}

    def open(self, path: Path, *, metadata: dict[str, Any] | None = None) -> None:
        self._writer = TdmsWriter(str(path))
        self._writer.open()
        properties: dict[str, Any] = {"format": "flex"}
        if metadata:
            properties["metadata"] = json.dumps(metadata, default=str)
        self._writer.write_segment([RootObject(properties=properties)])

    def add_columns(self, columns: list[ColumnSpec]) -> None:
        assert self._writer is not None, "open() first"
        self._units = {c.name: c.unit for c in columns}
        self._buffer = RowBuffer(columns, block_size=self._block_size)

    def append(self, row: dict[str, Any]) -> None:
        assert self._buffer is not None, "add_columns() first"
        if self._buffer.add(row):
            self._flush()

    def write_array(self, name: str, data: np.ndarray, *, attrs: dict[str, Any] | None = None) -> None:
        assert self._writer is not None, "open() first"
        self._writer.write_segment(
            [ChannelObject(_ARRAY_GROUP, name, np.asarray(data), properties=attrs or {})]
        )

    def close(self) -> None:
        if self._writer is None:
            return
        self._flush()
        self._writer.close()
        self._writer = None

    def _flush(self) -> None:
        if self._buffer is None or self._writer is None:
            return
        block = self._buffer.drain()
        if not block:
            return
        self._writer.write_segment(
            [
                ChannelObject(
                    _DATA_GROUP,
                    name,
                    values,
                    properties={"unit": self._units.get(name, "")},
                )
                for name, values in block.items()
            ]
        )
