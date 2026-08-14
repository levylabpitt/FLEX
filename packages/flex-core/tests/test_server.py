"""End-to-end station server tests over localhost ZMQ."""

import queue
import time

import pytest

from flex.client import connect
from flex.config import FlexConfig
from flex.instrument import Numbers, SimulatedInstrument
from flex.server import StationServer
from flex.station import Station


@pytest.fixture
def served():
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("gate", unit="V", vals=Numbers(-5, 5))
    sim.add_sim_parameter("x", initial=0.25, unit="V")
    station = Station({"bench": sim}, name="teststation")
    server = StationServer(station)  # random ports
    server.start()
    remote = connect(f"tcp://127.0.0.1:{server.port}", timeout=3.0)
    yield station, server, remote
    remote.close()
    server.stop()
    station.close()


def test_describe_and_proxies(served):
    station, server, remote = served
    assert remote.name == "teststation"
    assert list(remote.instruments) == ["bench"]
    bench = remote.bench
    assert set(bench.parameters) == {"gate", "x"}
    assert bench.parameters["gate"].unit == "V"


def test_remote_get_set(served):
    station, server, remote = served
    remote.bench.gate(1.5)
    assert remote.bench.gate() == 1.5
    assert station.bench.values["gate"] == 1.5  # actually reached the instrument


def test_remote_method_call_and_idn(served):
    station, server, remote = served
    assert remote.bench.idn()["model"] == "SimulatedInstrument"
    assert remote.bench.query("hello") == "hello"  # echo via __getattr__ proxy


def test_remote_validation_error(served):
    station, server, remote = served
    from flex.protocols import ZMQInstrumentError

    with pytest.raises(ZMQInstrumentError, match="outside"):
        remote.bench.gate(99)


def test_unknown_instrument_and_method(served):
    station, server, remote = served
    from flex.protocols import ZMQInstrumentError

    with pytest.raises(ZMQInstrumentError, match="No instrument"):
        remote._link.call("get", {"instrument": "nope", "parameter": "x"})
    with pytest.raises(ZMQInstrumentError, match="Unknown method"):
        remote._link.call("frobnicate")


def test_snapshot_over_wire(served):
    station, server, remote = served
    snap = remote.snapshot(read=True)
    assert snap["bench"]["parameters"]["x"]["value"] == 0.25


def test_event_stream(served):
    station, server, remote = served
    received: queue.Queue = queue.Queue()
    sub = remote.subscribe(received.put)
    time.sleep(0.3)  # let SUB join
    remote.bench.gate(2.0)
    event = received.get(timeout=3)
    assert event["event"] == "parameter.update"
    assert event["parameter"] == "bench.gate"
    assert event["value"] == 2.0
    assert event["kind"] == "set"
    assert isinstance(event["seq"], int)
    sub.stop()


def test_parameter_cache_local():
    sim = SimulatedInstrument("s")
    gate = sim.add_sim_parameter("gate")
    assert gate.cache is None
    gate(1.0)
    assert gate.cache == 1.0 and gate.cache_time is not None


def test_station_load_from_config():
    cfg = FlexConfig.model_validate({"instruments": {"bench": {"simulate": True}}})
    with Station.load(cfg) as station:
        assert station.bench.idn()["model"] == "SimulatedInstrument"


def test_background_logging(tmp_path):
    cfg = FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("x", initial=1.25, unit="V")
    station = Station({"bench": sim}, name="logstation", config=cfg)
    server = StationServer(station, monitor={"bench": (["x"], 0.1)})
    server.start()
    try:
        time.sleep(0.6)
    finally:
        server.stop()
        station.close()

    store = cfg.build_db()
    try:
        rows = store.list_monitor("bench.x")
        assert len(rows) >= 3  # several 0.1s polls landed
        assert rows[0].value == 1.25
        assert rows[0].unit == "V"
        assert rows[0].station == "logstation"
        assert store.list_monitor("bench.nope") == []
    finally:
        store.close()


def test_monitor_logs_remote_sets_too(tmp_path):
    cfg = FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("gate", unit="V")
    station = Station({"bench": sim}, name="logstation", config=cfg)
    server = StationServer(station, monitor={"bench": (["gate"], 60)})
    server.start()
    remote = connect(f"tcp://127.0.0.1:{server.port}", timeout=3.0)
    try:
        remote.bench.gate(0.7)
        time.sleep(0.5)  # let the writer thread land it
    finally:
        remote.close()
        server.stop()
        station.close()

    store = cfg.build_db()
    try:
        values = [r.value for r in store.list_monitor("bench.gate")]
        assert 0.7 in values
    finally:
        store.close()


def test_array_parameter_over_the_wire():
    import numpy as np

    sim = SimulatedInstrument("li")
    sim.add_parameter("waveform", getter=lambda: np.linspace(0, 1, 100), unit="V")
    station = Station({"li": sim}, name="t")
    server = StationServer(station)
    server.start()
    remote = connect(f"tcp://127.0.0.1:{server.port}", timeout=3.0)
    events = []
    remote.subscribe(events.append)
    try:
        wf = remote.li.waveform()
        assert wf == pytest.approx(list(np.linspace(0, 1, 100)))
        deadline = time.time() + 3
        while time.time() < deadline:
            values = [e["value"] for e in events
                      if e.get("parameter") == "li.waveform" and e.get("value") is not None]
            if values:
                break
            time.sleep(0.05)
        assert values and len(values[0]) == 100
    finally:
        remote.close()
        server.stop()
        station.close()


def test_serving_continues_when_db_unavailable_at_start(monkeypatch):
    cfg = FlexConfig.model_validate({"db": {"backend": "postgres", "dsn": "postgresql://nope/nope"}})
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("x", initial=1.0, unit="V")
    station = Station({"bench": sim}, name="s", config=cfg)
    server = StationServer(station, monitor={"bench": (["x"], 60)})
    server.start()
    try:
        remote = connect(f"tcp://127.0.0.1:{server.port}", timeout=3.0)
        assert remote.bench.x() == 1.0  # control plane unaffected by a dead DB
        remote.close()
    finally:
        server.stop()
        station.close()


def test_monitor_db_reconnects_after_startup_failure(tmp_path, monkeypatch):
    calls = {"n": 0}
    real_build = FlexConfig.build_db

    def flaky_build(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db not ready yet")
        return real_build(self)

    monkeypatch.setattr(FlexConfig, "build_db", flaky_build)
    monkeypatch.setattr("flex.server.time.sleep", lambda s: None)  # skip the 5s backoff

    cfg = FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("x", initial=2.0, unit="V")
    station = Station({"bench": sim}, name="s", config=cfg)
    server = StationServer(station, monitor={"bench": (["x"], 60)})
    server.start()
    try:
        deadline = time.time() + 3
        while calls["n"] < 2 and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.3)  # let the now-working store write the first poll
    finally:
        server.stop()
        station.close()

    assert calls["n"] >= 2
    store = cfg.build_db()
    try:
        assert store.list_monitor("bench.x")
    finally:
        store.close()


def test_monitor_write_retries_transient_failure(tmp_path, monkeypatch):
    cfg = FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("x", initial=9.0, unit="V")
    station = Station({"bench": sim}, name="s", config=cfg)
    server = StationServer(station, monitor={"bench": (["x"], 60)})

    from flex.db.sqlite import SQLiteStore

    real_record = SQLiteStore.record_monitor
    calls = {"n": 0}

    def flaky(self, record, **extra):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated transient lock")
        return real_record(self, record, **extra)

    monkeypatch.setattr(SQLiteStore, "record_monitor", flaky)
    server.start()
    try:
        time.sleep(1.0)  # first attempt fails, retry (0.2s backoff) succeeds
    finally:
        server.stop()
        station.close()

    assert calls["n"] >= 2
    store = cfg.build_db()
    try:
        assert store.list_monitor("bench.x")  # the record survived the retry
    finally:
        store.close()


def test_monitor_store_roundtrip_array(tmp_path):
    import numpy as np

    from flex.metadata import MonitorRecord

    cfg = FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
    store = cfg.build_db()
    try:
        store.record_monitor(MonitorRecord(parameter="spec.spectrum",
                                           value=np.linspace(0, 1, 5), station="s"))
        (row,) = store.list_monitor("spec.spectrum")
        assert row.value == [0.0, 0.25, 0.5, 0.75, 1.0]
    finally:
        store.close()
