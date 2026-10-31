"""The lock-in + PPMS example experiments, end to end: real drivers against
fake Instrument-Framework apps, behind a station server and the runner."""

import time
from pathlib import Path

import pytest

from flex.protocols.testing import FakeIFServer
from flex.runner import RunClient, RunServer
from flex.server import StationServer
from flex.station import Station
from flex_drivers.levylab.lockin import Lockin
from flex_drivers.levylab.ppms import PPMS

EXAMPLES = Path(__file__).parents[3] / "examples" / "experiments"


class FakeBench:
    """State shared by the two fake apps: temperature relaxes to its target,
    and the lock-in signal depends on temperature."""

    def __init__(self):
        self.temp = self.target = 300.0
        self.amplitude = 0.0
        self.state = "idle"

    def get_temperature(self, _params):
        self.temp += (self.target - self.temp) * 0.7
        status = "Stable" if abs(self.temp - self.target) < 0.05 else "Tracking"
        return {"temperature": self.temp, "status": status, "finished": status == "Stable"}

    def set_temperature(self, params):
        self.target = params["temperature"]
        return "ok"

    def set_state(self, params):
        self.state = "running"
        return "ok"

    def set_amplitude(self, params):
        self.amplitude = params["Amplitude"]
        return "ok"

    def results(self, _params):
        x = self.amplitude * (1 + self.temp / 1000)
        keys = {"AI1.Ref1.X": x, "AI1.Ref1.Y": x / 10, "AI1.Ref1.R": x, "AI1.Ref1.Theta": 1.0, "AI1.Mean": 0.0}
        return {"Results (Dictionary)": [{"key": k, "value": v} for k, v in keys.items()]}


@pytest.fixture
def stack(tmp_path, monkeypatch):
    config = tmp_path / "flex.toml"
    config.write_text(f'[data]\nroot = "{(tmp_path / "data").as_posix()}"\n[db]\nbackend = "sqlite"\n')
    monkeypatch.setenv("FLEX_CONFIG", str(config))

    bench = FakeBench()
    lockin_app = FakeIFServer({
        "getState": lambda _p: bench.state, "setState": bench.set_state,
        "setAO_Function": "ok", "setAO_Frequency": "ok", "setAO_Amplitude": bench.set_amplitude,
        "getResults": bench.results, "getAI": {"AI": 0.0}, "getAO": [{"Y": [0.0]}],
    })
    ppms_app = FakeIFServer({
        "getTemperature": bench.get_temperature, "setTemperature": bench.set_temperature,
        "getTemperatureTarget": lambda _p: bench.target,
        "getMagnet": 0.0, "getMagnetTarget": 0.0, "getLHeLevel": 55.0,
    })
    station = Station({"lockin": Lockin(address=lockin_app.address),
                       "ppms": PPMS(address=ppms_app.address)}, name="ppms-pc")
    server = StationServer(station)
    server.start()
    runner = RunServer([f"tcp://127.0.0.1:{server.port}"], root=tmp_path / "runs")
    runner.start()
    client = RunClient(f"tcp://127.0.0.1:{runner.port}", timeout=3.0)
    yield bench, lockin_app, ppms_app, client, tmp_path
    client.close()
    runner.stop()
    server.stop()
    station.close()
    lockin_app.stop()
    ppms_app.stop()


def test_probe_reports_every_call(stack):
    _, _, _, client, _ = stack
    done = client.wait(client.submit((EXAMPLES / "probe.py").read_text())["id"])
    assert done["status"] == "done", done["log"]
    text = "\n".join(done["log"])
    assert "ppms.get_temperature(): 300" in text
    assert "lockin.get_lockin_result(1, 'X')" in text
    assert "FAILED" not in text


def test_lockin_vs_temperature(stack):
    bench, lockin_app, ppms_app, client, tmp_path = stack
    params = {"points": 3, "start": 300.0, "stop": 296.0, "amplitude": 0.5, "tolerance": 0.3,
              "settle": 0.2, "poll": 0.05, "timeout": 30}
    done = client.wait(client.submit((EXAMPLES / "lockin_vs_temperature.py").read_text(), params=params)["id"])
    assert done["status"] == "done", done["log"]

    result = done["result"]
    assert [round(t) for t in result["T"]] == [300, 298, 296]
    assert all(x > 0 for x in result["X"])
    assert result["X"][0] > result["X"][2]  # signal falls as temperature does, as the fake app models

    targets = [r["params"]["temperature"] for r in ppms_app.requests if r["method"] == "setTemperature"]
    assert targets == [300.0, 298.0, 296.0]
    amplitudes = [r["params"]["Amplitude"] for r in lockin_app.requests if r["method"] == "setAO_Amplitude"]
    assert amplitudes == [0.5, 0]  # excitation on for the run, off afterwards
    assert any(p.suffix in (".h5", ".hdf5") for p in (tmp_path / "data").rglob("*"))


def test_abort_midway_still_switches_the_excitation_off(stack):
    _, lockin_app, _, client, _ = stack
    params = {"points": 2, "start": 100.0, "stop": 90.0, "amplitude": 0.5, "tolerance": 0.01,
              "settle": 60.0, "poll": 0.1, "timeout": 120}
    run = client.submit((EXAMPLES / "lockin_vs_temperature.py").read_text(), params=params)
    deadline = time.monotonic() + 60
    while "going to 100.00 K" not in client.run(run["id"])["log"] and time.monotonic() < deadline:
        time.sleep(0.1)
    assert "going to 100.00 K" in client.run(run["id"])["log"], "the script never started"
    client.abort(run["id"])
    done = client.wait(run["id"])
    assert done["status"] == "aborted"
    amplitudes = [r["params"]["Amplitude"] for r in lockin_app.requests if r["method"] == "setAO_Amplitude"]
    assert amplitudes[-1] == 0
