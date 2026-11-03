"""flex.marimo: connect through [hosts.*], submit a cell's function, view the run."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from flex import marimo as fm
from flex.instrument import Numbers, SimulatedInstrument
from flex.runner import RunServer
from flex.server import StationServer
from flex.station import Station


@pytest.fixture
def hub(tmp_path):
    sim = SimulatedInstrument("bench")
    sim.add_sim_parameter("gate", unit="V", vals=Numbers(-5, 5))
    station = Station({"bench": sim}, name="teststation")
    stations = StationServer(station)
    stations.start()
    runner = RunServer([f"tcp://127.0.0.1:{stations.port}"], root=tmp_path / "runs", abort_grace=5, token="s3cret")
    runner.start()
    config = tmp_path / "flex.toml"
    config.write_text(
        f'[hosts.ppms]\nhost = "127.0.0.1"\nstation_port = {stations.port}\n'
        f'runner_port = {runner.port}\ntoken = "s3cret"\n', encoding="utf-8")
    yield station, config
    runner.stop()
    stations.stop()
    station.close()


def test_connect_gives_the_live_station_and_a_runner_with_the_token(hub):
    station, config = hub
    remote, runs = fm.connect("ppms", config=config)
    try:
        assert remote.name == "teststation"
        remote.bench.gate(2.0)  # a real attribute, not __getattr__: completion sees it
        assert station.bench.values["gate"] == 2.0
        assert runs.runs() == []  # the runner demands the token, so it was passed
    finally:
        remote.close()
        runs.close()


def test_hosts_lists_the_configured_pcs(hub):
    _, config = hub
    assert fm.hosts(config) == ["ppms"]


def test_data_rows_picks_the_data_lines_out_of_a_log():
    log = ["cooldown 300 K", 'DATA {"T": 299.5, "G": 0.5}', "WARNING: x", 'DATA {"T": 299.0, "G": null}']
    assert fm.data_rows(log) == [{"T": 299.5, "G": 0.5}, {"T": 299.0, "G": None}]


def test_unknown_host_names_the_known_ones(hub):
    _, config = hub
    with pytest.raises(KeyError, match=r"No \[hosts.nope\].*have: ppms"):
        fm.connect("nope", config=config)


def test_submit_takes_a_function_from_a_cell(hub):
    station, config = hub
    remote, runs = fm.connect("ppms", config=config)
    try:
        def sweep(station, level=0):  # indented, like a function defined in a cell
            station.bench.gate(level)
            return {"gate": station.bench.gate()}

        rec = runs.submit(sweep, params={"level": 1.5})
        assert rec["name"] == "sweep"
        done = runs.wait(rec["id"])
        assert done["status"] == "done"
        assert done["result"] == {"gate": 1.5}
        assert station.bench.values["gate"] == 1.5
    finally:
        remote.close()
        runs.close()


@pytest.fixture
def hub_api():
    """A stand-in for the hub's notebook API, answering every GET with a title."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"data": {"meta": {"title": "Cooldown sweep"}}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _on_hub(monkeypatch, tmp_path, notebook_url):
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"notebook_url": notebook_url}), encoding="utf-8")
    monkeypatch.setenv("MARIMOHUB_CONTEXT_FILE", str(context))


def test_a_run_carries_its_hub_notebook_and_user(hub, hub_api, monkeypatch, tmp_path):
    _, config = hub
    url = f"{hub_api}/projects/proj-1/notebooks/nb-9"
    _on_hub(monkeypatch, tmp_path, url)
    remote, runs = fm.connect("ppms", user="alice", config=config)
    try:
        rec = runs.submit("def run(station): pass\n")
        assert runs.wait(rec["id"])["origin"] == {"user": "alice", "notebook": "Cooldown sweep", "url": url}
    finally:
        remote.close()
        runs.close()


def test_the_notebook_id_stands_in_when_the_hub_does_not_answer(hub, monkeypatch, tmp_path):
    _, config = hub
    _on_hub(monkeypatch, tmp_path, "http://127.0.0.1:9/projects/proj-1/notebooks/nb-9")  # nothing listens
    remote, runs = fm.connect("ppms", config=config)
    try:
        origin = runs.wait(runs.submit("def run(station): pass\n")["id"])["origin"]
        assert origin["notebook"] == "nb-9" and "user" not in origin
    finally:
        remote.close()
        runs.close()


def test_off_the_hub_only_the_user_is_known(hub, monkeypatch):
    _, config = hub
    monkeypatch.delenv("MARIMOHUB_CONTEXT_FILE", raising=False)
    monkeypatch.setenv("FLEX_USER", "bob")
    remote, runs = fm.connect("ppms", config=config)
    try:
        assert runs.wait(runs.submit("def run(station): pass\n")["id"])["origin"] == {"user": "bob"}
    finally:
        remote.close()
        runs.close()


def test_view_shows_status_log_and_result(hub):
    pytest.importorskip("marimo")
    _, config = hub
    remote, runs = fm.connect("ppms", user="alice", config=config)
    try:
        assert "No runs yet" in runs.view().text
        rec = runs.submit("def run(station):\n    print('hello log')\n    return {'x': 1}\n")
        runs.wait(rec["id"])
        shown = runs.view().text  # the latest run by default
        assert "done" in shown and "hello log" in shown and rec["id"] in shown and "by alice" in shown
    finally:
        remote.close()
        runs.close()
