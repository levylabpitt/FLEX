import pytest
from fastapi.testclient import TestClient

from flex.dashboard.app import create_app
from flex.instrument import SimulatedInstrument
from flex.server import StationServer
from flex.station import Station


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A dashboard over an isolated config + fresh SQLite in tmp_path."""
    config = tmp_path / "flex.toml"
    config.write_text(
        f'[data]\nroot = "{tmp_path.as_posix()}"\n'
        '[instruments.sim]\ndriver = "test.sim"\naddress = ""\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEX_CONFIG", str(config))
    return TestClient(create_app(), base_url="http://127.0.0.1")


@pytest.fixture
def served_station(tmp_path, monkeypatch):
    """A real StationServer plus a dashboard configured to talk to it."""
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("gate", unit="V")
    station = Station({"bench": sim}, name="uistation")
    server = StationServer(station)
    server.start()
    config = tmp_path / "flex.toml"
    config.write_text(
        f'[data]\nroot = "{tmp_path.as_posix()}"\n'
        f'[ui]\nstations = ["tcp://127.0.0.1:{server.port}"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEX_CONFIG", str(config))
    yield server, sim
    server.stop()
    station.close()


def test_station_tab_end_to_end(served_station):
    server, sim = served_station
    address = f"tcp://127.0.0.1:{server.port}"
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        (info,) = client.get("/api/stations").json()
        assert info["ok"] and info["station"] == "uistation"
        assert info["instruments"]["bench"]["parameters"]["gate"]["settable"]

        with client.websocket_connect("/ws/events") as ws:
            r = client.post("/api/stations/set", json={
                "address": address, "instrument": "bench", "parameter": "gate", "value": 0.7})
            assert r.status_code == 200
            assert sim.values["gate"] == 0.7
            for _ in range(10):  # the set's event reaches the browser socket
                event = ws.receive_json()
                if event.get("parameter") == "bench.gate":
                    assert event["value"] == 0.7
                    assert event["address"] == address
                    break
            else:
                raise AssertionError("no bench.gate event on the websocket")

        r = client.post("/api/stations/get", json={
            "address": address, "instrument": "bench", "parameter": "gate"})
        assert r.json()["value"] == 0.7

        r = client.post("/api/stations/get", json={
            "address": address, "instrument": "bench", "parameter": "nope"})
        assert r.status_code == 404


def test_station_tab_reports_unreachable_server(tmp_path, monkeypatch):
    config = tmp_path / "flex.toml"
    config.write_text(
        f'[data]\nroot = "{tmp_path.as_posix()}"\n'
        '[ui]\nstations = ["tcp://127.0.0.1:1"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEX_CONFIG", str(config))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        (info,) = client.get("/api/stations").json()
        assert not info["ok"]
        assert info["error"]


def test_index_serves_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "FLEX Dashboard" in response.text


def test_foreign_host_rejected(client):
    assert client.get("/api/drivers", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/drivers", headers={"host": "localhost:8756"}).status_code == 200


def test_drivers_listed(client):
    drivers = client.get("/api/drivers").json()
    assert any(d["name"] == "levylab.lockin" for d in drivers)


def test_shutdown_signals_process(client, monkeypatch):
    import signal
    import time as time_module

    calls = []
    monkeypatch.setattr("flex.dashboard.app.signal.raise_signal", lambda sig: calls.append(sig))
    monkeypatch.setattr("flex.dashboard.app.time.sleep", lambda seconds: None)

    response = client.post("/api/shutdown", json={})
    assert response.status_code == 200

    for _ in range(50):
        if calls:
            break
        time_module.sleep(0.02)
    assert calls == [signal.SIGINT]


def test_config_roundtrip(client, tmp_path):
    raw = client.get("/api/config/raw").json()
    assert raw["path"].endswith("flex.toml")
    assert "[instruments.sim" in raw["text"]

    response = client.put("/api/config/raw", json={"text": raw["text"] + '\n[lab]\nname = "x"\n'})
    assert response.status_code == 200
    assert client.get("/api/config").json()["config"]["lab"]["name"] == "x"


def test_invalid_config_rejected(client):
    response = client.put("/api/config/raw", json={"text": "[db]\nbackend = 3"})
    assert response.status_code == 422
    response = client.put("/api/config/raw", json={"text": "not toml ["})
    assert response.status_code == 422


def test_probe_driver(client, monkeypatch):
    from flex.instrument import SimulatedInstrument

    monkeypatch.setattr("flex.components.resolve_driver", lambda name: SimulatedInstrument)
    result = client.post("/api/drivers/levylab.lockin/probe", json={}).json()
    assert result["ok"] and result["idn"]["model"] == "SimulatedInstrument"


def test_probe_unresolvable_driver_reports_error(client):
    result = client.post("/api/drivers/acme.widget/probe", json={}).json()
    assert not result["ok"]
    assert "acme.widget" in result["error"]


def test_experiments_endpoints(client, tmp_path):
    from flex.config import FlexConfig
    from flex_exp import Experiment

    cfg = FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
    with Experiment("dash", name="demo", config=cfg, cell_log=False) as exp:
        with exp.measurement("IV") as m:
            m.add_row(x=1.0)
        exp.note("hello dashboard")

    experiments = client.get("/api/experiments").json()
    assert experiments[0]["user"] == "dash"

    detail = client.get(f"/api/experiments/{exp.id}").json()
    assert detail["measurements"][0]["id"] == m.id
    assert detail["measurements"][0]["file"]["uri"].endswith(".h5")
    assert any(n["text"] == "hello dashboard" for n in detail["notes"])

    assert client.get("/api/experiments/nope").status_code == 404


def test_writes_need_a_json_content_type(client):
    # another site's form post cannot send one without a CORS preflight
    assert client.post("/api/app/stop", content=b"", headers={"content-type": "text/plain"}).status_code == 403


def test_app_status_when_the_station_is_down(tmp_path, monkeypatch):
    import socket

    ports = []
    for _ in range(2):  # ports nothing is listening on, whatever else runs on this PC
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ports.append(s.getsockname()[1])
    config = tmp_path / "flex.toml"
    config.write_text(
        f'[data]\nroot = "{tmp_path.as_posix()}"\n[server]\nport = {ports[0]}\n[runner]\nport = {ports[1]}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEX_CONFIG", str(config))
    client = TestClient(create_app(), base_url="http://127.0.0.1")
    status = client.get("/api/app").json()
    assert status["station"] is False and status["runner"] is False
    assert status["managed"] is False
    assert client.post("/api/app/explode", json={}).status_code == 404


def test_runs_endpoints(tmp_path, monkeypatch):
    import time

    from flex.runner import RunClient, RunServer

    runner = RunServer([], root=tmp_path / "runs")
    runner.start()
    config = tmp_path / "flex.toml"
    config.write_text(f'[data]\nroot = "{tmp_path.as_posix()}"\n[runner]\nport = {runner.port}\n', encoding="utf-8")
    monkeypatch.setenv("FLEX_CONFIG", str(config))
    client = TestClient(create_app(), base_url="http://127.0.0.1")
    try:
        assert client.get("/api/runs").json() == []
        assert client.post("/api/runs/abort", json={}).status_code == 409  # nothing is running

        with RunClient(f"tcp://127.0.0.1:{runner.port}", timeout=3.0) as submitter:
            run_id = submitter.submit("def run(station):\n    print('hi')\n    return {'v': [1, 2, 3]}\n")["id"]
            submitter.wait(run_id)
        listed = client.get("/api/runs").json()
        assert [r["id"] for r in listed] == [run_id] and listed[0]["status"] == "done"
        detail = client.get(f"/api/runs/{run_id}").json()
        assert detail["log"] == ["hi"] and detail["result"] == {"v": [1, 2, 3]}
        assert client.get(f"/api/runs/{run_id}?since=1").json()["log"] == []  # only lines after `since`
    finally:
        runner.stop()
    time.sleep(0.2)
    assert client.get("/api/runs").status_code == 503


def test_station_tab_shows_failed_instruments_and_the_lease(served_station):
    from flex.protocols.zmq import ZMQInstrument

    server, _ = served_station
    server.station.failed["lockin"] = "no device"
    with ZMQInstrument("holder", f"tcp://127.0.0.1:{server.port}", timeout=3.0) as link:
        link.call("leaseAcquire", {"holder": "run-7", "token": "t", "ttl": 30})
        with TestClient(create_app(), base_url="http://127.0.0.1") as client:
            (info,) = client.get("/api/stations").json()
    assert info["failed"] == {"lockin": "no device"} and info["lease"] == "run-7"
