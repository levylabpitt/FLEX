import pytest
from asana.rest import ApiException

from flex_asana.client import AsanaClient, AsanaError


@pytest.fixture
def client():
    return AsanaClient(access_token="fake-token")


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ASANA_ACCESS_TOKEN"):
        AsanaClient()


def test_explicit_token_bypasses_env(monkeypatch):
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    AsanaClient(access_token="explicit")  # must not raise


def test_env_token_used_when_omitted(monkeypatch):
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "from-env")
    AsanaClient()  # must not raise


def test_call_wraps_api_exception_as_asana_error(client):
    def boom(*a, **k):
        raise ApiException(status=404, reason="not found")

    with pytest.raises(AsanaError, match="failed"):
        client._call(boom)


def test_collect_materializes_generator(client):
    def gen(*a, **k):
        yield from [{"gid": "1"}, {"gid": "2"}]

    assert client._collect(gen) == [{"gid": "1"}, {"gid": "2"}]


def test_data_drops_none_values():
    body = AsanaClient._data("name", "task", notes=None, assignee="u1")
    assert body == {"data": {"name": "task", "assignee": "u1"}}


def test_default_workspace_gid_single(client, monkeypatch):
    monkeypatch.setattr(client, "list_workspaces", lambda: [{"gid": "ws1", "name": "Lab"}])
    assert client.default_workspace_gid() == "ws1"


def test_default_workspace_gid_none_raises(client, monkeypatch):
    monkeypatch.setattr(client, "list_workspaces", lambda: [])
    with pytest.raises(AsanaError, match="No Asana workspaces"):
        client.default_workspace_gid()


def test_default_workspace_gid_multiple_raises(client, monkeypatch):
    monkeypatch.setattr(
        client, "list_workspaces", lambda: [{"gid": "1", "name": "A"}, {"gid": "2", "name": "B"}]
    )
    with pytest.raises(AsanaError, match="Multiple Asana workspaces"):
        client.default_workspace_gid()


def test_create_task_builds_expected_body(client, monkeypatch):
    captured = {}

    def fake_create_task(body, opts):
        captured["body"] = body
        captured["opts"] = opts
        return {"gid": "task1"}

    monkeypatch.setattr(client.tasks, "create_task", fake_create_task)
    result = client.create_task(
        "proj1", "Experiment X", notes=None, assignee="u1", custom_fields={"f1": "v1"}
    )
    assert result == {"gid": "task1"}
    assert captured["body"] == {
        "data": {
            "name": "Experiment X",
            "projects": ["proj1"],
            "assignee": "u1",
            "custom_fields": {"f1": "v1"},
        }
    }


def test_get_project_custom_field_specs_parses_response(client, monkeypatch):
    monkeypatch.setattr(
        client.projects,
        "get_project",
        lambda gid, opts: {
            "custom_field_settings": [
                {"custom_field": {"name": "Start Time", "gid": "f1", "resource_subtype": "date"}},
                {"custom_field": {"name": "End Time", "gid": "f2", "type": "text"}},
            ]
        },
    )
    specs = client.get_project_custom_field_specs("proj1")
    assert specs == {
        "Start Time": {"gid": "f1", "type": "date"},
        "End Time": {"gid": "f2", "type": "text"},
    }
