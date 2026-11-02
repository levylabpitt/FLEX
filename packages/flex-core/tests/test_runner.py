"""Experiment runner tests: real subprocesses against a real station server."""

import sqlite3
import time
from pathlib import Path

import pytest
import zmq

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


def test_abort_cuts_a_long_sleep_short(stack):
    _, _, client, _ = stack
    script = (
        "import time\n"
        "def run(station):\n"
        "    try:\n"
        "        print('waiting', flush=True)\n"
        "        time.sleep(120)\n"
        "    finally:\n"
        "        print('cleaned up', flush=True)\n"
    )
    rec = client.submit(script)
    _wait_for_line(client, rec["id"], "waiting")
    began = time.monotonic()
    client.abort(rec["id"])
    done = client.wait(rec["id"])
    assert done["status"] == "aborted" and "cleaned up" in done["log"]
    assert time.monotonic() - began < 8  # well inside the 10 s kill deadline


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


def test_a_stray_message_does_not_stop_the_runner(stack):
    _, runner, client, _ = stack
    stray = zmq.Context.instance().socket(zmq.DEALER)  # a REQ client sends [delimiter, payload]; this sends one frame
    stray.connect(f"tcp://127.0.0.1:{runner.port}")
    stray.send(b"hello")
    time.sleep(0.5)
    stray.close(linger=0)
    assert client.runs() == []


def test_a_run_records_where_it_came_from(stack):
    _, _, client, _ = stack
    rec = client.submit("def run(station): pass\n", name="a", origin={
        "user": "alice", "notebook": "flex_demo", "url": "http://hub/nb", "evil": "dropped", "empty": ""})
    done = client.wait(rec["id"])
    assert done["origin"] == {"user": "alice", "notebook": "flex_demo", "url": "http://hub/nb"}
    assert client.runs()[0]["origin"] == done["origin"]
    plain = client.wait(client.submit("def run(station): pass\n")["id"])
    assert plain["origin"] == {}


def test_a_runs_db_from_before_origins_still_opens(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    old = sqlite3.connect(root / "runs.db")
    old.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, name TEXT, status TEXT, entry TEXT, params TEXT, "
                "source_hash TEXT, started REAL, finished REAL, error TEXT, result TEXT, dir TEXT)")
    old.execute("INSERT INTO runs VALUES ('old', 'x', 'done', 'run', '{}', 'h', 1.0, 2.0, NULL, NULL, 'd')")
    old.commit()
    old.close()
    runner = RunServer([], root=root)
    runner.start()
    try:
        with RunClient(f"tcp://127.0.0.1:{runner.port}", timeout=3.0) as client:
            assert [(r["id"], r["origin"]) for r in client.runs()] == [("old", {})]
    finally:
        runner.stop()


def test_token_guards_every_call_but_ack(tmp_path):
    runner = RunServer([], root=tmp_path / "runs", token="s3cret")
    runner.start()
    address = f"tcp://127.0.0.1:{runner.port}"
    try:
        with RunClient(address, timeout=3.0) as anonymous:  # connecting (ACK) needs no token
            with pytest.raises(ZMQInstrumentError, match="Unauthorized"):
                anonymous.runs()
            with pytest.raises(ZMQInstrumentError, match="Unauthorized"):
                anonymous.submit("def run(station): pass\n")
        with RunClient(address, timeout=3.0, token="s3cret") as client:
            assert client.runs() == []
    finally:
        runner.stop()


def test_stopping_the_runner_aborts_a_run_with_its_cleanup(stack):
    station, runner, client, _ = stack
    station.bench.parameters["gate"].set(2.0)
    rec = client.submit(LONG)
    _wait_for_line(client, rec["id"], "started")
    runner.stop()  # the station is still up, so the script's finally block can reach it
    assert station.bench.values["gate"] == 0
    assert "cleaned up" in (Path(rec["dir"]) / "run.log").read_text()


def test_a_run_holds_the_station_until_it_ends(stack):
    from flex.client import connect

    station, runner, client, _ = stack
    station.bench.parameters["gate"].set(2.0)
    rec = client.submit(LONG)
    _wait_for_line(client, rec["id"], "started")
    with connect(runner.servers[0], timeout=3.0) as other:
        assert other.bench.gate() == 2.0  # reads pass
        with pytest.raises(ZMQInstrumentError, match=f"in use by {rec['id']}"):
            other.bench.gate(1.0)
        client.abort(rec["id"])
        client.wait(rec["id"])  # the script's own cleanup wrote through its lease
        assert other.bench.gate() == 0
        other.bench.gate(1.0)  # and the station is free again


def test_submit_is_all_or_nothing_across_servers(tmp_path):
    stations = [Station({"a": SimulatedInstrument("a")}, name="pc-a"),
                Station({"b": SimulatedInstrument("b")}, name="pc-b")]
    servers = [StationServer(s) for s in stations]
    for s in servers:
        s.start()
    addresses = [f"tcp://127.0.0.1:{s.port}" for s in servers]
    runner = RunServer(addresses, root=tmp_path / "runs")
    runner.start()
    try:
        from flex.protocols.zmq import ZMQInstrument

        with ZMQInstrument("other", addresses[1], timeout=3.0) as other:
            other.call("leaseAcquire", {"holder": "someone", "token": "x", "ttl": 30})
            with RunClient(f"tcp://127.0.0.1:{runner.port}", timeout=3.0) as client:
                with pytest.raises(ZMQInstrumentError, match="Cannot start.*in use by someone"):
                    client.submit("def run(station): pass\n")
                assert client.runs() == []
            with ZMQInstrument("first", addresses[0], timeout=3.0) as first:  # pc-a was released again
                assert first.call("leaseAcquire", {"holder": "me", "token": "y", "ttl": 30}) is True
    finally:
        runner.stop()
        for s in servers:
            s.stop()
        for st in stations:
            st.close()
