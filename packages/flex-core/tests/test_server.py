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
