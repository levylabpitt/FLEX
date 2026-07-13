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


def test_auto_display_live_updates_as_instruments_are_added(config, monkeypatch):
    """Any Experiment (not just CESession) gets a live-updating summary card
    in interactive sessions -- `with Experiment(...) as exp:` never makes
    exp the last expression of a cell, so this can't rely on _repr_html_
    alone."""
    import sys
    import types

    monkeypatch.setattr("flex.log.is_interactive", lambda: True)

    class Handle:
        display_id = "xyz"

    displayed, updated = [], []
    fake_display = types.ModuleType("IPython.display")
    fake_display.display = lambda html, display_id=None: displayed.append(html) or Handle()
    fake_display.update_display = lambda html, display_id: updated.append((html, display_id))
    fake_display.HTML = lambda s: s
    fake_ipython = types.ModuleType("IPython")
    fake_ipython.display = fake_display
    monkeypatch.setitem(sys.modules, "IPython", fake_ipython)
    monkeypatch.setitem(sys.modules, "IPython.display", fake_display)

    with Experiment("jane", config=config, cell_log=False) as exp:
        assert len(displayed) == 1  # shown immediately, before any instruments
        exp.add(SimulatedInstrument, "bench")
        assert len(updated) == 1
        assert "bench" in updated[0][0]
    assert len(updated) == 2  # end() refreshes once more (shows "Ended")
    assert "Ended" in updated[1][0]


def test_no_display_calls_outside_interactive(config):
    """Outside IPython, auto_display/refresh_display are no-ops -- no
    IPython import is attempted, and no error either way."""
    with Experiment("jane", config=config, cell_log=False) as exp:
        exp.add(SimulatedInstrument, "bench")
    assert exp._display_id is None


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


def test_comms_defaults_to_none(config):
    with Experiment("u", config=config) as exp:
        from flex.comms import NoComms

        assert isinstance(exp.comms, NoComms)


def test_comms_notify_start_and_end(config, monkeypatch):
    from flex.comms import CommsBackend

    calls = []

    class RecordingComms(CommsBackend):
        def notify_start(self, experiment):
            calls.append(("start", experiment.id))
            return "task-42"

        def notify_end(self, experiment, state):
            calls.append(("end", experiment.id, state))

    monkeypatch.setattr("flex.ecosystem.FlexConfig.build_comms", lambda self: RecordingComms())
    with Experiment("u", config=config) as exp:
        assert calls == [("start", exp.id)]
    assert calls == [("start", exp.id), ("end", exp.id, "task-42")]


def test_comms_build_failure_does_not_break_experiment(config, monkeypatch):
    monkeypatch.setattr(
        "flex.ecosystem.FlexConfig.build_comms",
        lambda self: (_ for _ in ()).throw(RuntimeError("no token")),
    )
    with Experiment("u", config=config) as exp:  # must not raise
        assert exp.comms is None


def test_comms_notify_failure_does_not_break_experiment(config, monkeypatch):
    from flex.comms import CommsBackend

    class BrokenComms(CommsBackend):
        def notify_start(self, experiment):
            raise RuntimeError("start boom")

        def notify_end(self, experiment, state):
            raise RuntimeError("end boom")

    monkeypatch.setattr("flex.ecosystem.FlexConfig.build_comms", lambda self: BrokenComms())
    with Experiment("u", config=config):  # must not raise, either at start or end
        pass


def test_notify_false_skips_comms_entirely(config, monkeypatch):
    from flex.comms import CommsBackend

    calls = []

    class RecordingComms(CommsBackend):
        def notify_start(self, experiment):
            calls.append("start")
            return None

        def notify_end(self, experiment, state):
            calls.append("end")

    monkeypatch.setattr("flex.ecosystem.FlexConfig.build_comms", lambda self: RecordingComms())
    with Experiment("u", config=config, notify=False) as exp:
        assert exp.comms is None
    assert calls == []


def test_user_type_falls_back_to_str_without_flex_asana(monkeypatch):
    """flex-exp must not hard-depend on flex-asana: block its import and
    confirm Experiment's `User` type hint degrades to plain str rather than
    failing to import at all."""
    import builtins
    import importlib
    import sys

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "flex_asana" or name.startswith("flex_asana."):
            raise ImportError("simulated: flex-asana not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    for mod in [m for m in sys.modules if m == "flex_asana" or m.startswith("flex_asana.")]:
        monkeypatch.delitem(sys.modules, mod)

    import flex_exp.experiment as experiment_module

    try:
        importlib.reload(experiment_module)
        assert experiment_module.User is str
    finally:
        importlib.reload(experiment_module)  # restore the real import for later tests


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
