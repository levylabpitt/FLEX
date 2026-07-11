"""Nextcloud storage backend: measurement files are written locally, then
uploaded via WebDAV when finalized. The local copy is kept as a cache.

Configuration::

    [storage]
    backend = "nextcloud"
    url = "https://nextcloud.example.org"
    user = "lab_shared"
    remote_root = "Data/FLEX"
    # password from the NEXTCLOUD_PASSWORD environment variable (recommended)
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import requests

from flex.data.storage import FilePointer, StorageBackend
from flex.log import get_logger

log = get_logger("nextcloud")


class NextcloudStorage(StorageBackend):
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        url: str,
        user: str,
        password: str | None = None,
        remote_root: str = "FLEX",
        session: requests.Session | None = None,
        **_options,
    ):
        if root is None:
            from flex.ecosystem import default_data_root

            root = default_data_root()
        self.root = Path(root)
        self.url = url.rstrip("/")
        self.user = user
        self.remote_root = PurePosixPath(remote_root.strip("/"))
        password = password or os.environ.get("NEXTCLOUD_PASSWORD")
        if not password:
            raise ValueError(
                "Nextcloud password missing: set the NEXTCLOUD_PASSWORD environment "
                "variable (or 'password' in [storage] — not recommended)"
            )
        self._session = session or requests.Session()
        self._session.auth = (user, password)

    # -- StorageBackend ------------------------------------------------------

    def new_measurement_path(self, experiment_id: str, measurement_id: str, suffix: str) -> Path:
        path = self.root / experiment_id[:4] / experiment_id / f"{measurement_id}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def finalize(self, local_path: Path) -> FilePointer:
        remote = self.remote_root / local_path.relative_to(self.root).as_posix()
        self._mkdirs(remote.parent)
        with open(local_path, "rb") as f:
            response = self._session.put(self._dav_url(remote), data=f, timeout=60)
        response.raise_for_status()
        log.info("Uploaded %s -> %s", local_path.name, remote)
        return FilePointer(
            uri=f"{self.url}/remote.php/dav/files/{self.user}/{remote}",
            backend="nextcloud",
            size=local_path.stat().st_size,
        )

    def open_local(self, pointer: FilePointer) -> Path:
        """Prefer the local cache; download from Nextcloud if it is gone."""
        prefix = f"{self.url}/remote.php/dav/files/{self.user}/{self.remote_root}/"
        if not pointer.uri.startswith(prefix):
            raise ValueError(f"Not a file under this Nextcloud storage ({prefix}): {pointer.uri}")
        relative = pointer.uri.removeprefix(prefix)
        local = self.root / Path(relative)
        if local.exists():
            return local
        local.parent.mkdir(parents=True, exist_ok=True)
        response = self._session.get(pointer.uri, timeout=60)
        response.raise_for_status()
        local.write_bytes(response.content)
        log.info("Downloaded %s", pointer.uri)
        return local

    def close(self) -> None:
        self._session.close()

    # -- internals ---------------------------------------------------------

    def _dav_url(self, remote: PurePosixPath) -> str:
        return f"{self.url}/remote.php/dav/files/{self.user}/{remote}"

    def _mkdirs(self, remote_dir: PurePosixPath) -> None:
        parts = remote_dir.parts
        for i in range(1, len(parts) + 1):
            url = self._dav_url(PurePosixPath(*parts[:i]))
            response = self._session.request("MKCOL", url, timeout=10)
            if response.status_code not in (201, 405):  # 405 = already exists
                response.raise_for_status()
