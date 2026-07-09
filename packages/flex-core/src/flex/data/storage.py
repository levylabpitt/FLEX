"""Storage backends: where finished measurement files live."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FilePointer:
    """A canonical reference to a stored measurement file."""

    uri: str
    backend: str = "local"
    size: int | None = None


class StorageBackend(ABC):
    """Decides where measurement files are written and what happens when they
    are finished. Writers always write locally; remote backends upload in
    :meth:`finalize` so network failures never touch a live measurement."""

    @abstractmethod
    def new_measurement_path(self, experiment_id: str, measurement_id: str, suffix: str) -> Path:
        """A local path for the writer to create (parents must exist)."""

    @abstractmethod
    def finalize(self, local_path: Path) -> FilePointer:
        """Called after the file is closed; move/upload and return the pointer."""

    def open_local(self, pointer: FilePointer) -> Path:
        """A local path for reading the file back (downloading if remote)."""
        return Path(pointer.uri)


class LocalStorage(StorageBackend):
    """The default: files stay on local disk under
    ``{root}/{year}/{experiment_id}/{measurement_id}{suffix}``."""

    def __init__(self, root: str | Path | None = None, **_options):
        if root is None:
            from flex.ecosystem import default_data_root

            root = default_data_root()
        self.root = Path(root)

    def new_measurement_path(self, experiment_id: str, measurement_id: str, suffix: str) -> Path:
        path = self.root / experiment_id[:4] / experiment_id / f"{measurement_id}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def finalize(self, local_path: Path) -> FilePointer:
        size = local_path.stat().st_size if local_path.exists() else None
        return FilePointer(uri=str(local_path), backend="local", size=size)
