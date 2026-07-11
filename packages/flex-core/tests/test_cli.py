import pytest
from typer.testing import CliRunner

from flex.cli import app

runner = CliRunner()


def test_list_packages():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "flex-core" in result.output
    assert "flex-datatypes" in result.output


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "flex-core" in result.output


def test_ecosystem_show_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("FLEX_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("flex.ecosystem.ACTIVE_CONFIG", tmp_path / "missing.toml")
    result = runner.invoke(app, ["ecosystem", "show"])
    assert result.exit_code == 0
    assert "built-in defaults" in result.output
    assert "sqlite" in result.output


def test_ecosystem_validate(tmp_path, monkeypatch):
    manifest = tmp_path / "lab.toml"
    manifest.write_text(
        '[ecosystem]\nname = "lab"\n[db]\nbackend = "sqlite"\n', encoding="utf-8"
    )
    result = runner.invoke(app, ["ecosystem", "validate", str(manifest)])
    assert result.exit_code == 0
    assert "Schema OK" in result.output
    assert "db: sqlite" in result.output


def test_experiments_and_measurements(tmp_path, monkeypatch):
    config = tmp_path / "flex.toml"
    config.write_text(f'[data]\nroot = "{tmp_path.as_posix()}"\n', encoding="utf-8")
    monkeypatch.setenv("FLEX_CONFIG", str(config))

    from flex.ecosystem import FlexConfig
    from flex_exp import Experiment

    with Experiment("cliuser", name="demo", config=FlexConfig.model_validate(
        {"data": {"root": str(tmp_path)}}
    ), cell_log=False) as exp:
        with exp.measurement("IV") as m:
            m.add_row(x=1.0)

    result = runner.invoke(app, ["experiments"])
    assert result.exit_code == 0
    assert "cliuser" in result.output

    result = runner.invoke(app, ["measurements", exp.id])
    assert result.exit_code == 0
    assert m.id in result.output


def test_new_driver(tmp_path):
    result = runner.invoke(app, ["new", "driver", "Keithley2400", "--out", str(tmp_path)])
    assert result.exit_code == 0
    code = (tmp_path / "keithley2400.py").read_text(encoding="utf-8")
    assert "class Keithley2400(VISAInstrument)" in code
    compile(code, "driver.py", "exec")  # generated code must be valid Python


def test_new_driver_zmq(tmp_path):
    result = runner.invoke(app, ["new", "driver", "MyIF", "--protocol", "zmq", "--out", str(tmp_path)])
    assert result.exit_code == 0
    assert "ZMQInstrument" in (tmp_path / "myif.py").read_text(encoding="utf-8")


def test_new_package(tmp_path):
    result = runner.invoke(app, ["new", "package", "flex-drivers-mylab", "--out", str(tmp_path)])
    assert result.exit_code == 0
    root = tmp_path / "flex-drivers-mylab"
    assert (root / "pyproject.toml").exists()
    init = (root / "src" / "flex_drivers_mylab" / "__init__.py").read_text(encoding="utf-8")
    assert "CATALOG" in init


def test_dashboard_launches(monkeypatch):
    calls = []
    monkeypatch.setattr("flex.dashboard.run", lambda **kw: calls.append(kw))
    result = runner.invoke(app, ["dashboard"])
    assert result.exit_code == 0
    assert calls == [{"host": "127.0.0.1", "port": 8756}]


def test_instruments_without_stations(monkeypatch, tmp_path):
    monkeypatch.delenv("FLEX_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("flex.ecosystem.ACTIVE_CONFIG", tmp_path / "missing.toml")
    result = runner.invoke(app, ["instruments"])
    assert result.exit_code == 0
    assert "No stations defined" in result.output


@pytest.mark.parametrize("cmd", [["--help"], ["ecosystem", "--help"], ["new", "--help"]])
def test_help_screens(cmd):
    assert runner.invoke(app, cmd).exit_code == 0
