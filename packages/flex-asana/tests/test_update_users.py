import flex_asana.update_users as update_users
from flex_asana.client import AsanaClient


def test_main_writes_generated_literal(monkeypatch, tmp_path):
    client = AsanaClient(access_token="fake-token")
    monkeypatch.setattr(update_users, "AsanaClient", lambda: client)
    monkeypatch.setattr(client, "default_workspace_gid", lambda: "ws1")
    monkeypatch.setattr(
        client, "list_users",
        lambda ws: [
            {"email": "jane.doe@lab.org", "gid": "u1"},
            {"email": "john.smith@lab.org", "gid": "u2"},
        ],
    )
    out = tmp_path / "_generated_users.py"
    monkeypatch.setattr(update_users, "_OUT", out)

    update_users.main()

    content = out.read_text(encoding="utf-8")
    assert 'User = Literal[' in content
    assert "'jane.doe'" in content
    assert "'john.smith'" in content

    namespace: dict = {}
    exec(content, namespace)
    assert namespace["User"].__args__ == ("jane.doe", "john.smith")


def test_main_raises_on_empty_workspace(monkeypatch, tmp_path):
    import pytest

    client = AsanaClient(access_token="fake-token")
    monkeypatch.setattr(update_users, "AsanaClient", lambda: client)
    monkeypatch.setattr(client, "default_workspace_gid", lambda: "ws1")
    monkeypatch.setattr(client, "list_users", lambda ws: [])
    monkeypatch.setattr(update_users, "_OUT", tmp_path / "_generated_users.py")

    with pytest.raises(RuntimeError, match="No Asana users found"):
        update_users.main()
