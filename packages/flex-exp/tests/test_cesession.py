"""CESession tests: sanitized Configure Experiments fixture + fake IF servers."""

import json
from pathlib import Path

import pytest

from flex_exp.sessions.ce import CESession, parse_ce_config

zmq = pytest.importorskip("zmq")
from flex_protocols.testing import FakeIFServer  # noqa: E402
from flex_protocols.zmq import ZMQInstrument  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "control_experiment.json"


class FakeLockin(ZMQInstrument):
    lv_class = "Instrument.Lockin.lvclass"


class FakeKH(ZMQInstrument):
    lv_class = "Instrument.KH7008.lvclass"


@pytest.fixture
def servers(tmp_path):
    """Two fake IF apps + a CE file whose addresses point at them."""
    with FakeIFServer() as lockin_server, FakeIFServer() as kh_server:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["Experiment"]["Instruments"][0]["Address"] = lockin_server.address
        raw["Experiment"]["Instruments"][1]["Address"] = kh_server.address
        ce_path = tmp_path / "Control Experiment.json"
        ce_path.write_text(json.dumps(raw), encoding="utf-8")
        yield ce_path, lockin_server, kh_server


REGISTRY = {
    "Instrument.Lockin.lvclass": FakeLockin,
    "Instrument.KH7008.lvclass": FakeKH,
}


def test_parse_ce_config():
    info = parse_ce_config(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert info.user == "jane.doe"
    assert info.device == "SA40001A"
    assert info.station == "PPMS-1"
    # the generic instrument-types stub is skipped
    assert [i["Type"] for i in info.instruments] == ["DAQ", "Amplifier"]
    # empty electrodes are skipped
    assert info.wiring == {1: ("S", "source"), 2: ("D", "drain"), 4: ("TG", "top gate")}
    assert info.timestamp.year == 2026


def test_session_connects_instruments(servers, config):
    ce_path, lockin_server, kh_server = servers
    with CESession(
        ce_path=ce_path, config=config, driver_registry=REGISTRY, transport_server=False,
        cell_log=False,
    ) as exp:
        assert exp.user == "jane.doe"
        assert exp.name == "SA40001A"
        assert isinstance(exp.DAQ, FakeLockin)
        assert isinstance(exp.Amplifier, FakeKH)
        assert exp.get_device_path() == Path("C:/Data/Devices/SA40001A")
        assert exp.wiring[1] == ("S", "source")
        # both fake apps received the connection ACK
        assert lockin_server.requests[0]["method"] == "ACK"
        assert kh_server.requests[0]["method"] == "ACK"
        html = exp._repr_html_()
        assert "SA40001A" in html and "FakeLockin" in html and "top gate" in html


def test_missing_driver_is_actionable(servers, config):
    import logging

    from flex_db.sqlite import SQLiteStore

    ce_path, *_ = servers
    with pytest.raises(RuntimeError, match="No driver for 'Instrument.Lockin.lvclass'"):
        CESession(
            ce_path=ce_path, config=config, driver_registry={}, transport_server=False,
            cell_log=False,
        )
    # the half-built Experiment was cleaned up: file log detached, record ended
    handlers = logging.getLogger("flex").handlers
    assert not [h for h in handlers if isinstance(h, logging.FileHandler)]
    store = SQLiteStore(path=config.data.root / "flex.db")
    (rec,) = store.list_experiments()
    assert rec.end_time is not None
    store.close()


def test_verbose_prints_connection_progress(servers, config, capsys):
    ce_path, *_ = servers
    with CESession(
        ce_path=ce_path, config=config, driver_registry=REGISTRY, transport_server=False,
        cell_log=False, verbose=True,
    ):
        pass
    out = capsys.readouterr().out
    assert "Connecting to DAQ" in out
    assert "Connecting to Amplifier" in out


def test_quiet_by_default(servers, config, capsys):
    """Without verbose, no per-instrument print() narration -- the usual
    logging (checked elsewhere) still applies."""
    ce_path, *_ = servers
    with CESession(
        ce_path=ce_path, config=config, driver_registry=REGISTRY, transport_server=False,
        cell_log=False,
    ):
        pass
    assert "Connecting to" not in capsys.readouterr().out


def test_auto_displays_html_when_interactive(servers, config, monkeypatch):
    """In a `with CESession() as exp:` block this object is never the last
    expression of a cell, so _repr_html_ alone would never render -- it must
    be pushed to display() explicitly when running interactively, then kept
    live as each instrument connects."""
    import sys
    import types

    ce_path, *_ = servers
    monkeypatch.setattr("flex.log.is_interactive", lambda: True)

    class Handle:
        display_id = "abc123"

    displayed, updated = [], []
    fake_display = types.ModuleType("IPython.display")
    fake_display.display = lambda html, display_id=None: displayed.append(html) or Handle()
    fake_display.update_display = lambda html, display_id: updated.append((html, display_id))
    fake_display.HTML = lambda s: s
    fake_ipython = types.ModuleType("IPython")
    fake_ipython.display = fake_display
    monkeypatch.setitem(sys.modules, "IPython", fake_ipython)
    monkeypatch.setitem(sys.modules, "IPython.display", fake_display)

    with CESession(
        ce_path=ce_path, config=config, driver_registry=REGISTRY, transport_server=False,
        cell_log=False,
    ):
        pass

    assert len(displayed) == 1  # the initial card, at construction
    # one live refresh per instrument connected, plus one at end()
    assert len(updated) == 3
    assert all(display_id == "abc123" for _, display_id in updated)
    assert "DAQ" in updated[0][0]


def test_missing_ce_file_is_actionable(tmp_path, config):
    with pytest.raises(FileNotFoundError, match="Configure Experiments"):
        CESession(ce_path=tmp_path / "nope.json", config=config, driver_registry=REGISTRY)


def test_update_connects_new_instruments(servers, config, tmp_path):
    ce_path, lockin_server, kh_server = servers
    raw = json.loads(ce_path.read_text(encoding="utf-8"))
    trimmed = dict(raw)
    trimmed["Experiment"] = dict(raw["Experiment"])
    trimmed["Experiment"]["Instruments"] = raw["Experiment"]["Instruments"][:1]
    ce_path.write_text(json.dumps(trimmed), encoding="utf-8")

    with CESession(
        ce_path=ce_path, config=config, driver_registry=REGISTRY, transport_server=False,
        cell_log=False,
    ) as exp:
        assert list(exp.instruments) == ["DAQ"]
        ce_path.write_text(json.dumps(raw), encoding="utf-8")  # amplifier plugged in
        exp.update()
        assert isinstance(exp.Amplifier, FakeKH)


def test_measurement_works_on_cesession(servers, config, tmp_path):
    """CESession is a full Experiment: scans and files work unchanged."""
    ce_path, *_ = servers
    with CESession(
        ce_path=ce_path, config=config, driver_registry=REGISTRY, transport_server=False,
        cell_log=False,
    ) as exp:
        with exp.measurement("check") as m:
            m.add_row(x=1.0)
    assert m.file is not None and m.file.uri.endswith(".h5")
