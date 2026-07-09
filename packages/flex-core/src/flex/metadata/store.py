"""Metadata records and the store interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from flex.data.storage import FilePointer


@dataclass
class ExperimentRecord:
    id: str
    user: str
    name: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    instruments: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class MeasurementRecord:
    id: str
    experiment_id: str
    name: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    file: FilePointer | None = None
    aborted: bool = False


@dataclass
class NoteRecord:
    experiment_id: str
    text: str
    measurement_id: str | None = None
    time: datetime | None = None
    kind: str = "note"  # "note" | "cell" | "log"


class MetadataStore(ABC):
    """Records the experiment lifecycle and answers queries about it.

    ``**extra`` on the record methods lets lab backends persist additional
    data (e.g. wiring tables) without changing this interface. Implementations
    must ignore extras they do not understand.
    """

    # -- writing ----------------------------------------------------------

    @abstractmethod
    def record_experiment_start(self, record: ExperimentRecord, **extra: Any) -> None: ...

    @abstractmethod
    def record_experiment_end(
        self, experiment_id: str, end_time: datetime, instruments: list[str], **extra: Any
    ) -> None: ...

    @abstractmethod
    def record_measurement_start(self, record: MeasurementRecord, **extra: Any) -> None: ...

    @abstractmethod
    def record_measurement_end(
        self,
        measurement_id: str,
        end_time: datetime,
        file: FilePointer | None,
        aborted: bool = False,
        **extra: Any,
    ) -> None: ...

    @abstractmethod
    def record_note(self, record: NoteRecord, **extra: Any) -> None: ...

    # -- reading ----------------------------------------------------------

    @abstractmethod
    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None: ...

    @abstractmethod
    def list_experiments(
        self, *, user: str | None = None, limit: int = 50
    ) -> list[ExperimentRecord]: ...

    @abstractmethod
    def list_measurements(self, experiment_id: str) -> list[MeasurementRecord]: ...

    @abstractmethod
    def list_notes(self, experiment_id: str) -> list[NoteRecord]: ...

    @abstractmethod
    def close(self) -> None: ...
