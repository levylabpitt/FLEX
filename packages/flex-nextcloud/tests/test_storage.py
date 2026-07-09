from pathlib import PurePosixPath

import pytest

from flex_nextcloud import NextcloudStorage


class FakeResponse:
    def __init__(self, status_code=201, content=b""):
        self.status_code = status_code
        self.content = content
        self.ok = status_code < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.auth = None
        self.calls = []
        self.files: dict[str, bytes] = {}

    def request(self, method, url, timeout=None):
        self.calls.append((method, url))
        return FakeResponse(201)

    def put(self, url, data=None, timeout=None):
        self.files[url] = data.read()
        self.calls.append(("PUT", url))
        return FakeResponse(201)

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        return FakeResponse(200, self.files.get(url, b"remote-bytes"))


@pytest.fixture
def storage(tmp_path):
    return NextcloudStorage(
        tmp_path,
        url="https://cloud.example.org/",
        user="lab",
        password="secret",
        remote_root="Data/FLEX",
        session=FakeSession(),
    )


def test_finalize_uploads_with_mkcol(storage, tmp_path):
    path = storage.new_measurement_path("20260709120000-ab", "20260709120100-cd", ".h5")
    path.write_bytes(b"payload")
    pointer = storage.finalize(path)

    session = storage._session
    mkcols = [url for method, url in session.calls if method == "MKCOL"]
    assert any(url.endswith("Data/FLEX/2026/20260709120000-ab") for url in mkcols)
    assert pointer.backend == "nextcloud"
    assert pointer.uri.startswith("https://cloud.example.org/remote.php/dav/files/lab/Data/FLEX/")
    assert session.files[pointer.uri] == b"payload"
    assert pointer.size == 7


def test_open_local_prefers_cache(storage):
    path = storage.new_measurement_path("20260709120000-ab", "m1", ".h5")
    path.write_bytes(b"cached")
    pointer = storage.finalize(path)
    assert storage.open_local(pointer) == path
    assert ("GET", pointer.uri) not in storage._session.calls


def test_open_local_downloads_when_missing(storage):
    path = storage.new_measurement_path("20260709120000-ab", "m2", ".h5")
    path.write_bytes(b"payload")
    pointer = storage.finalize(path)
    path.unlink()
    local = storage.open_local(pointer)
    assert local.read_bytes() == b"payload"


def test_missing_password_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXTCLOUD_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="NEXTCLOUD_PASSWORD"):
        NextcloudStorage(tmp_path, url="https://x", user="u")


def test_remote_layout(storage):
    remote = storage.remote_root
    assert remote == PurePosixPath("Data/FLEX")
