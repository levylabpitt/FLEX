from flex.pkgmanager import ecosystems


def test_list_bundled_includes_official_manifests():
    names = {e["name"] for e in ecosystems.list_bundled()}
    assert {"default", "levylab"} <= names
    levylab = next(e for e in ecosystems.list_bundled() if e["name"] == "levylab")
    assert "flex-nextcloud" in levylab["packages"]


def test_resolve_by_name():
    path = ecosystems.resolve("levylab")
    assert path is not None
    assert path.is_file()
    assert path.read_text(encoding="utf-8").startswith("#")  # the manifest's header comment


def test_resolve_unknown_returns_none():
    assert ecosystems.resolve("not-a-real-ecosystem") is None


def test_resolve_by_internal_name(tmp_path, monkeypatch):
    manifest = tmp_path / "somefile.toml"
    manifest.write_text('[ecosystem]\nname = "mylab"\n', encoding="utf-8")
    monkeypatch.setattr(ecosystems, "_dirs", lambda: [tmp_path])
    assert ecosystems.resolve("mylab") == manifest
