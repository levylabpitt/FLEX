import h5py
import numpy as np
import pytest

from flex.data import ColumnSpec, FilePointer, HDF5Writer, LocalStorage


def test_hdf5_roundtrip(tmp_path):
    path = tmp_path / "meas.h5"
    writer = HDF5Writer(block_size=3)  # small block to exercise flushing
    writer.open(path, metadata={"experiment": "e1", "user": "test"})
    writer.add_columns([ColumnSpec("gate", "V"), ColumnSpec("current", "A")])
    for i in range(7):
        writer.append({"gate": i * 0.1, "current": i * 1e-9})
    writer.write_array("spectrum", np.arange(5.0), attrs={"channel": 1})
    writer.close()
    writer.close()  # idempotent

    with h5py.File(path) as f:
        assert f.attrs["rows"] == 7
        assert "experiment" in f.attrs["metadata"]
        np.testing.assert_allclose(f["data/gate"][:], np.arange(7) * 0.1)
        assert f["data/gate"].attrs["unit"] == "V"
        assert f["data/current"].shape == (7,)
        np.testing.assert_allclose(f["arrays/spectrum"][:], np.arange(5.0))
        assert f["arrays/spectrum"].attrs["channel"] == 1


def test_hdf5_missing_column_is_nan_unknown_rejected(tmp_path):
    writer = HDF5Writer()
    writer.open(tmp_path / "m.h5")
    writer.add_columns([ColumnSpec("x"), ColumnSpec("y")])
    writer.append({"x": 1.0})  # y -> NaN
    with pytest.raises(KeyError, match="Unknown column"):
        writer.append({"z": 1.0})
    writer.close()

    with h5py.File(tmp_path / "m.h5") as f:
        assert np.isnan(f["data/y"][0])


def test_local_storage_layout(tmp_path):
    storage = LocalStorage(tmp_path)
    path = storage.new_measurement_path("20260709120000-abcd", "20260709120100-ef01", ".h5")
    assert path == tmp_path / "2026" / "20260709120000-abcd" / "20260709120100-ef01.h5"
    assert path.parent.is_dir()

    path.write_bytes(b"data")
    pointer = storage.finalize(path)
    assert pointer == FilePointer(uri=str(path), backend="local", size=4)
    assert storage.open_local(pointer) == path
