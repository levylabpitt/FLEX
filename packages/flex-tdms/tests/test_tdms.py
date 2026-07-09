import numpy as np
from nptdms import TdmsFile

from flex.data import ColumnSpec
from flex_tdms import TDMSWriter


def test_roundtrip(tmp_path):
    path = tmp_path / "meas.tdms"
    writer = TDMSWriter(block_size=3)
    writer.open(path, metadata={"experiment_id": "e1"})
    writer.add_columns([ColumnSpec("gate", "V"), ColumnSpec("current", "A")])
    for i in range(7):
        writer.append({"gate": i * 0.1, "current": i * 1e-9})
    writer.write_array("spectrum", np.arange(4.0), attrs={"channel": 2})
    writer.close()
    writer.close()  # idempotent

    tdms = TdmsFile.read(path)
    assert "e1" in tdms.properties["metadata"]
    gate = tdms["Data.000000"]["gate"]
    np.testing.assert_allclose(gate[:], np.arange(7) * 0.1)
    assert gate.properties["unit"] == "V"
    np.testing.assert_allclose(tdms["Data.000000"]["current"][:], np.arange(7) * 1e-9)
    spectrum = tdms["Arrays"]["spectrum"]
    np.testing.assert_allclose(spectrum[:], np.arange(4.0))
    assert spectrum.properties["channel"] == 2


def test_writer_resolves_via_registry(tmp_path):
    from flex.ecosystem import FlexConfig

    cfg = FlexConfig.model_validate({"data": {"writer": "tdms", "root": str(tmp_path)}})
    writer = cfg.build_writer()
    assert isinstance(writer, TDMSWriter)
