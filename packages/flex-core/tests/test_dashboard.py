import pytest
from fastapi.testclient import TestClient

from flex.dashboard.app import create_app


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
    return TestClient(create_app(), base_url="http://127.0.0.1")


def test_index_serves_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "FLEX Dashboard" in response.text


def test_foreign_host_rejected(client):
    assert client.get("/api/packages", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/packages", headers={"host": "localhost:8756"}).status_code == 200


def test_unknown_package_install_404(client):
    assert client.post("/api/packages/not-a-package/install").status_code == 404
    assert client.post("/api/packages/not-a-package/remove").status_code == 404


def test_packages_and_drivers(client):
    packages = client.get("/api/packages").json()
    assert any(p["name"] == "flex-core" and p["installed"] for p in packages)
    drivers = client.get("/api/drivers").json()
    assert any(d["name"] == "levylab.lockin" for d in drivers)


def test_removed_package_stays_listed_for_reinstall(client, monkeypatch):
    """An uninstalled package stays listed (as not-installed)."""
    monkeypatch.setattr(
        "flex.pkgmanager.manager.installed_version",
        lambda name: None if name == "flex-nextcloud" else "2.0.0a1",
    )
    packages = client.get("/api/packages").json()
    entry = next(p for p in packages if p["name"] == "flex-nextcloud")
    assert entry["installed"] is None
    assert entry["group"] == "Integrations"


def test_ecosystems_lists_manifests(client):
    result = client.get("/api/ecosystems").json()
    names = {e["name"] for e in result["available"]}
    assert {"default", "levylab"} <= names
    assert result["active"] == "default"


def test_shutdown_signals_process(client, monkeypatch):
    import signal
    import time as time_module

    calls = []
    monkeypatch.setattr("flex.dashboard.app.signal.raise_signal", lambda sig: calls.append(sig))
    monkeypatch.setattr("flex.dashboard.app.time.sleep", lambda seconds: None)

    response = client.post("/api/shutdown")
    assert response.status_code == 200

    for _ in range(50):
        if calls:
            break
        time_module.sleep(0.02)
    assert calls == [signal.SIGINT]


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


def test_probe_driver(client, monkeypatch):
    from flex.instrument import SimulatedInstrument

    monkeypatch.setattr(
        "flex.pkgmanager.PackageManager.resolve_driver", lambda self, name: SimulatedInstrument
    )
    result = client.post("/api/drivers/levylab.lockin/probe").json()
    assert result["ok"] and result["idn"]["model"] == "SimulatedInstrument"


def test_probe_unresolvable_driver_reports_error(client):
    result = client.post("/api/drivers/acme.widget/probe").json()
    assert not result["ok"]
    assert "acme.widget" in result["error"]


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
