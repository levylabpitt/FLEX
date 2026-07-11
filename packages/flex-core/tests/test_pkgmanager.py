import pytest

from flex.pkgmanager import PackageManager, load_catalog
from flex.pkgmanager.manager import _workspace_root

FAKE_CATALOG = {
    "flex-core": {"group": "Core", "summary": "core", "default": True},
    "flex-drivers": {
        "group": "Drivers",
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
    assert catalog["flex-datatypes"]["provides"]["writer"] == ["hdf5", "tdms"]


def test_list_packages_marks_installed(manager):
    packages = {p.name: p for p in manager.list_packages()}
    assert packages["flex-core"].installed  # running from the workspace
    assert packages["flex-core"].default


def test_install_skips_present(manager):
    manager.install("flex-core")
    assert manager.commands == []


def test_install_with_extras_runs_even_if_base_installed(manager, monkeypatch):
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: "2.0.0")
    manager.install("flex-db[postgres]")
    (cmd,) = manager.commands
    assert "install" in cmd


def test_install_runs_installer(manager, monkeypatch):
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: None)
    manager.install("flex-datatypes")
    (cmd,) = manager.commands
    assert "install" in cmd


def test_install_uses_editable_path_for_workspace_members(manager, monkeypatch):
    """Workspace members install editable, not by (unpublished) name."""
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: None)
    manager.install("flex-datatypes")
    (cmd,) = manager.commands
    assert cmd[-2:] == ["-e", str(_workspace_root() / "packages" / "flex-datatypes")]


def test_install_falls_back_to_github_source_outside_workspace(manager, monkeypatch):
    """Outside a checkout, install from GitHub source, not a bare name."""
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: None)
    monkeypatch.setattr("flex.pkgmanager.manager._workspace_root", lambda: None)
    manager.install("flex-nextcloud")
    (cmd,) = manager.commands
    assert cmd[-1] == (
        "flex-nextcloud @ git+https://github.com/levylabpitt/flex.git"
        "@v2#subdirectory=packages/flex-nextcloud"
    )


def test_list_drivers_from_catalog(manager, monkeypatch):
    monkeypatch.setattr("flex.pkgmanager.manager.installed_version", lambda p: None)
    drivers = {d.name: d for d in manager.list_drivers()}
    assert set(drivers) == {"levylab.lockin", "levylab.ppms"}
    assert not drivers["levylab.lockin"].available
    assert not drivers["levylab.lockin"].enabled


def test_run_installer_explains_self_locked_exe(monkeypatch):
    """A `flex dashboard` launched via flex.exe holds its own launcher file
    locked on Windows; translate that specific uv failure into a fix, not a
    raw stack trace."""
    import subprocess

    from flex.pkgmanager.manager import PackageManager

    locked = subprocess.CompletedProcess(
        args=["uv"],
        returncode=2,
        stdout="",
        stderr="error: failed to remove file `...Scripts/flex.exe`: "
        "The process cannot access the file because it is being used by another process.",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: locked)
    with pytest.raises(RuntimeError, match="python -m flex dashboard"):
        PackageManager._run_installer(["uv", "pip", "install"])


def test_run_installer_removes_regenerated_exe_on_windows(monkeypatch, tmp_path):
    """install.ps1 replaces Scripts/flex.exe with a flex.cmd shim so `flex`
    never self-locks; every subsequent install regenerates flex.exe anyway
    (uv reconciles all console scripts), so it must be deleted again each time
    so PATHEXT keeps preferring the .cmd."""
    import subprocess

    from flex.pkgmanager import manager as manager_module
    from flex.pkgmanager.manager import PackageManager

    (tmp_path / "flex.cmd").write_text("@echo off\r\n")
    (tmp_path / "flex.exe").write_bytes(b"stub")
    ok = subprocess.CompletedProcess(args=["uv"], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: ok)
    monkeypatch.setattr(manager_module.sys, "platform", "win32")
    monkeypatch.setattr(manager_module.sys, "executable", str(tmp_path / "python.exe"))

    PackageManager._run_installer(["uv", "pip", "install"])

    assert not (tmp_path / "flex.exe").exists()
    assert (tmp_path / "flex.cmd").exists()


def test_run_installer_leaves_exe_alone_without_shim(monkeypatch, tmp_path):
    """No flex.cmd (dev workspace / non-Windows-installer setups) -> don't
    touch flex.exe at all."""
    import subprocess

    from flex.pkgmanager import manager as manager_module
    from flex.pkgmanager.manager import PackageManager

    (tmp_path / "flex.exe").write_bytes(b"stub")
    ok = subprocess.CompletedProcess(args=["uv"], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: ok)
    monkeypatch.setattr(manager_module.sys, "platform", "win32")
    monkeypatch.setattr(manager_module.sys, "executable", str(tmp_path / "python.exe"))

    PackageManager._run_installer(["uv", "pip", "install"])

    assert (tmp_path / "flex.exe").exists()


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
    assert cmd[-2:] == ["-e", str(_workspace_root() / "packages" / "flex-drivers")]


def test_unknown_driver_message(manager):
    from flex.components import ComponentError

    with pytest.raises(ComponentError, match="Unknown driver"):
        manager.enable_driver("acme.widget")
