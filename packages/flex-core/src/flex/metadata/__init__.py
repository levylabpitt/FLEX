"""FLEX experiment metadata: what happened, when, by whom, and where the data is.

The store interface is backend-agnostic; ``flex-db`` provides SQLite (default)
and PostgreSQL implementations. Actual measurement data lives in files (see
``flex.data``) — the metadata store only indexes it.
"""

from flex.metadata.store import (
    CellRecord,
    ExperimentRecord,
    InstrumentRecord,
    LogEntryRecord,
    MeasurementRecord,
    MetadataStore,
    NoteRecord,
)

__all__ = [
    "CellRecord",
    "ExperimentRecord",
    "InstrumentRecord",
    "LogEntryRecord",
    "MeasurementRecord",
    "MetadataStore",
    "NoteRecord",
]
