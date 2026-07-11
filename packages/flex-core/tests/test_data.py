from flex.data import FilePointer, LocalStorage


def test_local_storage_layout(tmp_path):
    storage = LocalStorage(tmp_path)
    path = storage.new_measurement_path("20260709120000-abcd", "20260709120100-ef01", ".h5")
    assert path == tmp_path / "2026" / "20260709120000-abcd" / "20260709120100-ef01.h5"
    assert path.parent.is_dir()

    path.write_bytes(b"data")
    pointer = storage.finalize(path)
    assert pointer == FilePointer(uri=str(path), backend="local", size=4)
    assert storage.open_local(pointer) == path
