"""Experiment runner tests: real subprocesses against a real station server."""

import time

import pytest

from flex.client import StationGroup
from flex.instrument import Numbers, SimulatedInstrument
from flex.protocols.zmq import ZMQInstrumentError
from flex.runner import RunClient, RunServer
from flex.server import StationServer
from flex.station import Station


@pytest.fixture
def stack(tmp_path):
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("gate", unit="V", vals=Numbers(-5, 5))
    station = Station({"bench": sim}, name="teststation")
    stations = StationServer(station)
    stations.start()
    runner = RunServer([f"tcp://127.0.0.1:{stations.port}"], root=tmp_path / "runs", abort_grace=5)
    runner.start()
    client = RunClient(f"tcp://127.0.0.1:{runner.port}", timeout=3.0)
    yield station, runner, client, tmp_path
    client.close()
    runner.stop()
    stations.stop()
    station.close()


def test_run_finishes_with_result_and_log(stack):
    station, _, client, _ = stack
    rec = client.submit(
        "def run(station, level=0):\n"
        "    station.bench.gate(level)\n"
        "    print('gate set')\n"
        "    return {'gate': station.bench.gate()}\n",
        params={"level": 1.5}, name="setgate",
    )
    done = client.wait(rec["id"])
    assert done["status"] == "done"
    assert done["result"] == {"gate": 1.5}
    assert done["params"] == {"level": 1.5}
    assert "gate set" in done["log"]
    assert station.bench.values["gate"] == 1.5


def test_failed_run_keeps_the_error_and_traceback(stack):
    _, _, client, _ = stack
    rec = client.submit("def run(station):\n    raise ValueError('boom')\n")
    done = client.wait(rec["id"])
    assert done["status"] == "failed"
    assert done["error"] == "ValueError: boom"
    assert any("Traceback" in line for line in done["log"])


def test_missing_entry_function_fails_clearly(stack):
    _, _, client, _ = stack
    done = client.wait(client.submit("x = 1\n")["id"])
    assert done["status"] == "failed"
    assert "no function 'run'" in done["error"]


def test_syntax_error_is_rejected_at_submit(stack):
    _, _, client, _ = stack
    with pytest.raises(ZMQInstrumentError, match="submitted script"):
        client.submit("def run(station:\n")
    assert client.runs() == []


LONG = (
    "import time\n"
    "def run(station):\n"
    "    print('started', flush=True)\n"
    "    try:\n"
    "        while True:\n"
    "            time.sleep(0.1)\n"
    "    finally:\n"
    "        station.bench.gate(0)\n"
    "        print('cleaned up', flush=True)\n"
)


def _wait_for_line(client, run_id, text, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if text in client.run(run_id)["log"]:
            return
        time.sleep(0.1)
    raise AssertionError(f"'{text}' never appeared in the log")


def test_one_run_at_a_time(stack):
    _, _, client, _ = stack
    first = client.submit(LONG)
    _wait_for_line(client, first["id"], "started")
    with pytest.raises(ZMQInstrumentError, match="Busy"):
        client.submit("def run(station): pass\n")
    client.abort()
    client.wait(first["id"])


def test_abort_runs_the_scripts_cleanup(stack):
    station, _, client, _ = stack
    station.bench.parameters["gate"].set(2.0)
    rec = client.submit(LONG)
    _wait_for_line(client, rec["id"], "started")
    client.abort(rec["id"])
    done = client.wait(rec["id"])
    assert done["status"] == "aborted"
    assert "cleaned up" in done["log"]
    assert station.bench.values["gate"] == 0  # the finally block ran


def test_events_stream_status_and_log(stack):
    _, runner, client, _ = stack
    events = []
    sub = client.subscribe(events.append)
    time.sleep(0.3)  # let the SUB socket connect
    rec = client.submit("def run(station):\n    print('hello')\n")
    client.wait(rec["id"])
    time.sleep(0.3)
    sub.stop()
    assert ("run.log", "hello") in [(e["event"], e.get("line")) for e in events]
    assert [e["status"] for e in events if e["event"] == "run.status"] == ["running", "done"]
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)


def test_run_records_survive_and_stale_runs_are_marked_interrupted(tmp_path):
    first = RunServer([], root=tmp_path / "runs")
    first._db.execute("INSERT INTO runs (id, status, params, started) VALUES ('old', 'running', '{}', 0)")
    first._db.commit()
    first.stop()
    second = RunServer([], root=tmp_path / "runs")
    try:
        assert second._record("old")["status"] == "interrupted"
    finally:
        second.stop()


def test_station_group_merges_servers_and_rejects_duplicates():
    a, b = SimulatedInstrument("lockin"), SimulatedInstrument("gate")
    sa, sb = Station({"lockin": a}, name="pc-a"), Station({"gate": b}, name="pc-b")
    ta, tb = StationServer(sa), StationServer(sb)
    ta.start()
    tb.start()
    try:
        group = StationGroup([f"tcp://127.0.0.1:{ta.port}", f"tcp://127.0.0.1:{tb.port}"], timeout=3.0)
        assert set(group.instruments) == {"lockin", "gate"}
        assert group.lockin.idn()["model"] == "SimulatedInstrument"
        group.close()

        clash = Station({"lockin": SimulatedInstrument("lockin")}, name="pc-c")
        tc = StationServer(clash)
        tc.start()
        with pytest.raises(ValueError, match="more than one"):
            StationGroup([f"tcp://127.0.0.1:{ta.port}", f"tcp://127.0.0.1:{tc.port}"], timeout=3.0)
        tc.stop()
    finally:
        ta.stop()
        tb.stop()
