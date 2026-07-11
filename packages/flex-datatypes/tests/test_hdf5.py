import h5py
import numpy as np
import pytest

from flex.data import ColumnSpec
from flex_datatypes.hdf5 import HDF5Writer


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


def test_writer_resolves_via_registry(tmp_path):
    from flex.ecosystem import FlexConfig

    cfg = FlexConfig.model_validate({"data": {"writer": "hdf5", "root": str(tmp_path)}})
    writer = cfg.build_writer()
    assert isinstance(writer, HDF5Writer)
