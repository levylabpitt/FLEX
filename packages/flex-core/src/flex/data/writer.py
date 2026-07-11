"""The data writer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class ColumnSpec:
    """One column of tabular measurement data."""

    name: str
    unit: str = ""
    dtype: Any = float


class DataWriter(ABC):
    """Writes one measurement's data file.

    Lifecycle: ``open`` → ``add_columns`` → ``append``/``write_array`` (any
    number of times) → ``close``. Implementations must tolerate ``close``
    being called early (aborted measurements) and must flush what they have.
    """

    format_name: str = ""
    suffix: str = ""

    @abstractmethod
    def open(self, path: Path, *, metadata: dict[str, Any] | None = None) -> None:
        """Create the file at ``path`` and store ``metadata`` in it."""

    @abstractmethod
    def add_columns(self, columns: list[ColumnSpec]) -> None:
        """Declare the tabular columns (before the first ``append``)."""

    @abstractmethod
    def append(self, row: dict[str, Any]) -> None:
        """Append one data point. Missing columns are recorded as NaN."""

    @abstractmethod
    def write_array(self, name: str, data: np.ndarray, *, attrs: dict[str, Any] | None = None) -> None:
        """Store a named free-form array (spectra, images, waveforms)."""

    @abstractmethod
    def close(self) -> None:
        """Flush and close the file. Must be safe to call more than once."""


@dataclass
class RowBuffer:
    """Utility for writers: buffers rows per column, flushing in blocks."""

    columns: list[ColumnSpec]
    block_size: int = 1000
    _pending: dict[str, list] = field(default_factory=dict)

    def __post_init__(self):
        self._pending = {c.name: [] for c in self.columns}

    def add(self, row: dict[str, Any]) -> bool:
        """Buffer one row; returns True when a flush is due."""
        unknown = set(row) - set(self._pending)
        if unknown:
            raise KeyError(f"Unknown column(s): {', '.join(sorted(unknown))}")
        for name, values in self._pending.items():
            values.append(row.get(name, np.nan))
        return len(next(iter(self._pending.values()), [])) >= self.block_size

    def drain(self) -> dict[str, np.ndarray]:
        """Return and clear the buffered block as {column: array}."""
        block = {name: np.asarray(values) for name, values in self._pending.items()}
        for values in self._pending.values():
            values.clear()
        return block
