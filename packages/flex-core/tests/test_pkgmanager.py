import pytest

from flex.pkgmanager import PackageManager, load_catalog

FAKE_CATALOG = {
    "flex-core": {"group": "Core", "summary": "core", "default": True},
    "flex-drivers-levylab": {
        "group": "LevyLab Drivers",
        "summary": "levylab drivers",
        "drivers": ["levylab.lockin", "levylab.ppms"],
    },
}


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("flex.pkgmanager.manager.load_catalog", lambda: FAKE_CATALOG)
    commands = []
    pm = PackageManager(config_path=tmp_path / "config.toml", runner=commands.append)
    pm.commands = commands
    return pm


def test_catalog_loads_real_file():
    catalog = load_catalog()
    assert "flex-core" in catalog
    assert catalog["flex-tdms"]["provides"]["flex.writers"] == ["tdms"]


def test_list_packages_marks_installed(manager):
    packages = {p.name: p for p in manager.list_packages()}
    assert packages["flex-core"].installed  # running from the workspace
    assert packages["flex-core"].default


def test_install_skips_present(manager):
    manager.install("flex-core")
    assert manager.commands == []


def test_install_runs_installer(manager, monkeypatch):
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: None)
    manager.install("flex-tdms")
    (cmd,) = manager.commands
    assert cmd[-1] == "flex-tdms"
    assert "install" in cmd


def test_list_drivers_from_catalog(manager, monkeypatch):
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: None)
    drivers = {d.name: d for d in manager.list_drivers()}
    assert set(drivers) == {"levylab.lockin", "levylab.ppms"}
    assert not drivers["levylab.lockin"].available
    assert not drivers["levylab.lockin"].enabled


def test_enable_disable_driver_roundtrip(manager, tmp_path):
    info = manager.enable_driver("levylab.lockin")
    assert info.enabled
    config = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "levylab.lockin" in config

    drivers = {d.name: d for d in manager.list_drivers()}
    assert drivers["levylab.lockin"].enabled

    manager.disable_driver("levylab.lockin")
    drivers = {d.name: d for d in manager.list_drivers()}
    assert not drivers["levylab.lockin"].enabled


def test_enable_installs_missing_package(manager, monkeypatch):
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: None)
    manager.enable_driver("levylab.ppms")
    (cmd,) = manager.commands
    assert cmd[-1] == "flex-drivers-levylab"


def test_unknown_driver_message(manager):
    from flex.components import ComponentError

    with pytest.raises(ComponentError, match="Unknown driver"):
        manager.enable_driver("acme.widget")
