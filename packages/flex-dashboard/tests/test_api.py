import pytest
from fastapi.testclient import TestClient

from flex_dashboard.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A dashboard over an isolated config + fresh SQLite in tmp_path."""
    config = tmp_path / "flex.toml"
    config.write_text(
        f'[data]\nroot = "{tmp_path.as_posix()}"\n'
        '[stations.bench.instruments.sim]\ndriver = "test.sim"\naddress = ""\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEX_CONFIG", str(config))
    return TestClient(create_app())


def test_index_serves_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "FLEX Dashboard" in response.text


def test_packages_and_drivers(client):
    packages = client.get("/api/packages").json()
    assert any(p["name"] == "flex-core" and p["installed"] for p in packages)
    drivers = client.get("/api/drivers").json()
    assert any(d["name"] == "levylab.lockin" for d in drivers)


def test_config_roundtrip(client, tmp_path):
    raw = client.get("/api/config/raw").json()
    assert raw["path"].endswith("flex.toml")
    assert "[stations.bench" in raw["text"]

    response = client.put("/api/config/raw", json={"text": raw["text"] + '\n[lab]\nname = "x"\n'})
    assert response.status_code == 200
    assert client.get("/api/config").json()["config"]["lab"]["name"] == "x"


def test_invalid_config_rejected(client):
    response = client.put("/api/config/raw", json={"text": "[db]\nbackend = 3"})
    assert response.status_code == 422
    response = client.put("/api/config/raw", json={"text": "not toml ["})
    assert response.status_code == 422


def test_stations_and_probe_error(client, monkeypatch):
    stations = client.get("/api/stations").json()
    assert stations["bench"]["sim"]["driver"] == "test.sim"

    from flex.instrument import SimulatedInstrument

    monkeypatch.setattr(
        "flex.pkgmanager.PackageManager.resolve_driver", lambda self, name: SimulatedInstrument
    )
    result = client.post("/api/instruments/bench/sim/probe").json()
    assert result["ok"] and result["idn"]["model"] == "SimulatedInstrument"

    assert client.post("/api/instruments/bench/nope/probe").status_code == 404


def test_experiments_endpoints(client, tmp_path):
    from flex.ecosystem import FlexConfig
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
