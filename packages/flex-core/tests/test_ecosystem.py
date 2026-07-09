from pathlib import Path

import pytest

from flex.ecosystem import FlexConfig, default_data_root, find_config, load_config

MANIFEST = """
[ecosystem]
name = "testlab"
packages = ["flex-tdms"]

[lab]
name = "testlab"
station = "cryo-1"

[db]
backend = "postgres"
dsn = "postgresql://example.org/lab"

[data]
writer = "hdf5"
root = "D:/data"

[hooks]
on_experiment_end = ["os.path:join"]

[drivers]
enabled = ["levylab.lockin"]

[stations.cryo1.instruments.lockin]
driver = "levylab.lockin"
address = "tcp://localhost:29170"
"""


def test_defaults_without_config(monkeypatch, tmp_path):
    monkeypatch.delenv("FLEX_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("flex.ecosystem.ACTIVE_CONFIG", tmp_path / "missing.toml")
    cfg = load_config()
    assert cfg.source is None
    assert cfg.db.backend == "sqlite"
    assert cfg.data.writer == "hdf5"
    assert cfg.storage.backend == "local"
    assert cfg.exp.handler == "default"
    assert cfg.data.root == default_data_root()


def test_load_manifest(tmp_path):
    path = tmp_path / "testlab.toml"
    path.write_text(MANIFEST, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.source == path
    assert cfg.ecosystem.name == "testlab"
    assert cfg.ecosystem.packages == ["flex-tdms"]
    assert cfg.db.backend == "postgres"
    assert cfg.db.options() == {"dsn": "postgresql://example.org/lab"}
    assert cfg.data.root == Path("D:/data")
    assert cfg.drivers.enabled == ["levylab.lockin"]
    inst = cfg.stations["cryo1"].instruments["lockin"]
    assert inst.driver == "levylab.lockin"
    assert inst.address == "tcp://localhost:29170"


def test_find_config_precedence(monkeypatch, tmp_path):
    explicit = tmp_path / "explicit.toml"
    env = tmp_path / "env.toml"
    cwd_cfg = tmp_path / "cwd" / "flex.toml"
    cwd_cfg.parent.mkdir()
    for p in (explicit, env, cwd_cfg):
        p.write_text("", encoding="utf-8")

    monkeypatch.chdir(cwd_cfg.parent)
    monkeypatch.setenv("FLEX_CONFIG", str(env))
    assert find_config(explicit) == explicit
    assert find_config() == env
    monkeypatch.delenv("FLEX_CONFIG")
    assert find_config() == cwd_cfg


def test_missing_explicit_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")


def test_build_bus_subscribes_hooks(tmp_path):
    path = tmp_path / "eco.toml"
    path.write_text(MANIFEST, encoding="utf-8")
    bus = load_config(path).build_bus()
    assert bus._subscribers.get("experiment.end"), "hook should be subscribed"


def test_unloadable_hook_is_skipped(tmp_path):
    path = tmp_path / "eco.toml"
    path.write_text('[hooks]\non_experiment_end = ["not_a_module:missing"]\n', encoding="utf-8")
    bus = load_config(path).build_bus()  # must not raise
    assert not bus._subscribers.get("experiment.end")


def test_config_roundtrips_extra_sections(tmp_path):
    path = tmp_path / "eco.toml"
    path.write_text("[myext]\ncustom = 1\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.model_extra["myext"] == {"custom": 1}
    assert isinstance(cfg, FlexConfig)
