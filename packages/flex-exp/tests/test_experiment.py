from typing import Protocol, runtime_checkable

import h5py
import numpy as np
import pytest

from flex.instrument import SimulatedInstrument
from flex_db.sqlite import SQLiteStore
from flex_exp import Experiment


@runtime_checkable
class Temperature(Protocol):
    """A minimal capability protocol, for testing structural conformance."""

    def get_temperature(self) -> float: ...
    def set_temperature(self, setpoint: float, *, rate: float | None = None) -> None: ...


def test_end_to_end_measurement(config, tmp_path):
    with Experiment("jane", name="demo", config=config) as exp:
        sim = exp.add(SimulatedInstrument, "lockin")
        gate = sim.add_sim_parameter("gate", unit="V")

        with exp.measurement("IV") as m:
            m.register(sim.parameters["gate"])
            for v in np.linspace(0, 1, 5):
                gate(v)
                m.read_point(current=v * 1e-9)
        assert m.rows == 5
        assert m.file is not None

    # data file round-trip
    with h5py.File(m.file.uri) as f:
        np.testing.assert_allclose(f["data/lockin.gate"][:], np.linspace(0, 1, 5))
        assert f["data/lockin.gate"].attrs["unit"] == "V"
        assert f["data/current"].shape == (5,)
        assert "snapshot" in f.attrs["metadata"]

    # metadata round-trip
    store = SQLiteStore(path=tmp_path / "flex.db")
    record = store.get_experiment(exp.id)
    assert record.user == "jane"
    assert record.end_time is not None
    assert record.instruments == ["lockin"]
    (meas,) = store.list_measurements(exp.id)
    assert meas.name == "IV"
    assert not meas.aborted
    assert meas.file.uri == m.file.uri
    store.close()

    # experiment log file exists and mentions the measurement
    log_file = tmp_path / exp.id[:4] / exp.id / "experiment.log"
    assert "Measurement" in log_file.read_text(encoding="utf-8")


def test_instrument_registry_and_capabilities(config):
    class FakeCryostat(SimulatedInstrument):
        def get_temperature(self) -> float:
            return 4.2

        def set_temperature(self, setpoint, *, rate=None):
            pass

    with Experiment("u", config=config) as exp:
        exp.add(FakeCryostat, "cryo")
        assert exp.cryo is exp.get("cryo")
        assert exp.get(FakeCryostat) is exp.cryo
        assert exp.get(Temperature) is exp.cryo
        with pytest.raises(KeyError, match="No instrument 'magnet'"):
            exp.get("magnet")
        with pytest.raises(ValueError, match="already registered"):
            exp.add(SimulatedInstrument, "cryo", name="cryo")
        with pytest.raises(AttributeError):
            _ = exp.nonexistent


def test_notes_and_events(config, tmp_path):
    events = []
    exp = Experiment("u", config=config, notes="cooldown 12")
    exp.events.subscribe("measurement.end", lambda event, **kw: events.append(event))
    with exp:
        with exp.measurement() as m:
            m.add_row(x=1.0)
            m.add_note("first point")
    assert events == ["measurement.end"]

    store = SQLiteStore(path=tmp_path / "flex.db")
    notes = store.list_notes(exp.id)
    assert [n.text for n in notes] == ["cooldown 12", "first point"]
    assert notes[1].measurement_id == m.id
    store.close()


def test_aborted_measurement_is_finalized(config, tmp_path):
    with Experiment("u", config=config) as exp:
        with pytest.raises(KeyboardInterrupt):
            with exp.measurement("sweep") as m:
                m.add_row(x=0.0)
                raise KeyboardInterrupt

    with h5py.File(m.file.uri) as f:  # file was closed and finalized
        assert f["data/x"].shape == (1,)

    store = SQLiteStore(path=tmp_path / "flex.db")
    (meas,) = store.list_measurements(exp.id)
    assert meas.aborted
    store.close()


def test_writer_close_failure_still_records_end(config, tmp_path):
    def bad_close():
        raise OSError("disk full")

    with Experiment("u", config=config) as exp:
        with exp.measurement("m") as m:
            m.add_row(x=1.0)
            m._writer.close = bad_close

    store = SQLiteStore(path=tmp_path / "flex.db")
    (meas,) = store.list_measurements(exp.id)
    assert meas.end_time is not None
    assert not meas.aborted
    store.close()


def test_metadata_store_failure_does_not_break_experiment(config, monkeypatch):
    monkeypatch.setattr(
        "flex.ecosystem.FlexConfig.build_db",
        lambda self: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    with Experiment("u", config=config) as exp:  # must not raise
        with exp.measurement() as m:
            m.add_row(x=1.0)
    assert m.file is not None


def test_load_station(config, monkeypatch):
    config.stations = {}
    cfg = config.model_copy()
    cfg_dict = cfg.model_dump()
    cfg_dict["stations"] = {
        "bench": {"instruments": {"sim1": {"driver": "test.sim", "address": "sim://x"}}}
    }
    from flex.ecosystem import FlexConfig

    cfg = FlexConfig.model_validate(cfg_dict)

    class AddressedSim(SimulatedInstrument):
        def __init__(self, name, address):
            super().__init__(name)
            self._address = address

    monkeypatch.setattr(
        "flex.pkgmanager.PackageManager.resolve_driver", lambda self, name: AddressedSim
    )
    with Experiment("u", config=cfg) as exp:
        exp.load_station()
        assert exp.sim1.address == "sim://x"
