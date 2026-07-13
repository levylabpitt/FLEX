from datetime import UTC, datetime

import pytest

from flex_asana.client import AsanaClient, AsanaError
from flex_asana.sync import ExperimentSync, handle_from_user


def test_handle_from_user_prefers_email():
    assert handle_from_user({"email": "Jane.Doe@LevyLab.org", "name": "Jane Doe"}) == "jane.doe"


def test_handle_from_user_falls_back_to_name():
    assert handle_from_user({"email": "", "name": "Jane Doe"}) == "jane.doe"


def test_handle_from_user_none_when_empty():
    assert handle_from_user({}) is None


@pytest.fixture
def client():
    return AsanaClient(access_token="fake-token")


def test_missing_project_gid_raises(client, monkeypatch):
    monkeypatch.delenv("ASANA_EXPERIMENTS_PROJECT_GID", raising=False)
    with pytest.raises(ValueError, match="project gid required"):
        ExperimentSync(client=client, workspace_gid="ws1")


def test_workspace_gid_falls_back_to_default(client, monkeypatch):
    monkeypatch.setattr(client, "default_workspace_gid", lambda: "ws-auto")
    sync = ExperimentSync(client=client, project_gid="proj1")
    assert sync.workspace_gid == "ws-auto"


def test_resolve_user_gid_caches_and_warns_on_miss(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        client, "list_users",
        lambda ws: calls.append(ws) or [{"email": "jane.doe@lab.org", "gid": "u1"}],
    )
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")

    assert sync.resolve_user_gid("jane.doe") == "u1"
    assert sync.resolve_user_gid("jane.doe") == "u1"
    assert len(calls) == 1  # cached, not refetched

    assert sync.resolve_user_gid("nobody") is None


def test_resolve_user_gid_never_raises_on_lookup_failure(client, monkeypatch):
    def boom(ws):
        raise AsanaError("list_users failed: 403")

    monkeypatch.setattr(client, "list_users", boom)
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")

    assert sync.resolve_user_gid("jane.doe") is None  # must not raise


def test_start_experiment_creates_unassigned_task_when_lookup_fails(client, monkeypatch):
    monkeypatch.setattr(client, "get_project_custom_field_specs", lambda gid: {})
    monkeypatch.setattr(client, "list_users", lambda ws: (_ for _ in ()).throw(AsanaError("down")))
    captured = {}
    monkeypatch.setattr(
        client, "create_task",
        lambda project_gid, name, **kw: captured.update(kw) or {"gid": "task1"},
    )
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")

    gid = sync.start_experiment("jane", "Experiment X", datetime.now())

    assert gid == "task1"  # task still created
    assert captured["assignee"] is None  # just unassigned


def test_custom_field_value_date_type(client, monkeypatch):
    monkeypatch.setattr(
        client, "get_project_custom_field_specs",
        lambda gid: {"Start Time": {"gid": "f1", "type": "date"}},
    )
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")
    when = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    gid, value = sync._custom_field_value("Start Time", when)
    assert gid == "f1"
    assert value == {"date_time": when.astimezone().isoformat()}


def test_custom_field_value_text_type(client, monkeypatch):
    monkeypatch.setattr(
        client, "get_project_custom_field_specs",
        lambda gid: {"Start Time": {"gid": "f1", "type": "text"}},
    )
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")
    when = datetime(2026, 7, 13, 12, 0, 0)
    gid, value = sync._custom_field_value("Start Time", when)
    assert gid == "f1"
    assert value == when.isoformat(sep=" ", timespec="seconds")


def test_custom_field_value_missing_field_returns_none(client, monkeypatch):
    monkeypatch.setattr(client, "get_project_custom_field_specs", lambda gid: {})
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")
    assert sync._custom_field_value("Start Time", datetime.now()) == (None, None)


def test_start_experiment_creates_task_with_start_field_and_assignee(client, monkeypatch):
    monkeypatch.setattr(
        client, "get_project_custom_field_specs",
        lambda gid: {"Start Time": {"gid": "f1", "type": "text"}},
    )
    monkeypatch.setattr(client, "list_users", lambda ws: [{"email": "jane@lab.org", "gid": "u1"}])
    captured = {}

    def fake_create_task(project_gid, name, **kw):
        captured.update(project_gid=project_gid, name=name, **kw)
        return {"gid": "task1"}

    monkeypatch.setattr(client, "create_task", fake_create_task)
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")

    gid = sync.start_experiment("jane", "Experiment X", datetime(2026, 7, 13, 9, 0, 0))

    assert gid == "task1"
    assert captured["project_gid"] == "proj1"
    assert captured["name"] == "Experiment X"
    assert captured["assignee"] == "u1"
    assert "f1" in captured["custom_fields"]


def test_start_experiment_without_assign_user_leaves_task_unassigned(client, monkeypatch):
    monkeypatch.setattr(client, "get_project_custom_field_specs", lambda gid: {})
    captured = {}
    monkeypatch.setattr(
        client, "create_task",
        lambda project_gid, name, **kw: captured.update(kw) or {"gid": "task1"},
    )
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1", assign_user=False)

    sync.start_experiment("jane", "Experiment X", datetime.now())
    assert captured["assignee"] is None


def test_end_experiment_updates_task(client, monkeypatch):
    monkeypatch.setattr(
        client, "get_project_custom_field_specs",
        lambda gid: {"End Time": {"gid": "f2", "type": "text"}},
    )
    captured = {}
    monkeypatch.setattr(
        client, "update_task", lambda task_gid, **kw: captured.update(task_gid=task_gid, **kw)
    )
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")

    sync.end_experiment("task1", datetime(2026, 7, 13, 17, 0, 0))
    assert captured["task_gid"] == "task1"
    assert "f2" in captured["custom_fields"]


def test_end_experiment_noop_when_field_missing(client, monkeypatch):
    monkeypatch.setattr(client, "get_project_custom_field_specs", lambda gid: {})
    called = []
    monkeypatch.setattr(client, "update_task", lambda *a, **k: called.append((a, k)))
    sync = ExperimentSync(client=client, workspace_gid="ws1", project_gid="proj1")

    sync.end_experiment("task1", datetime.now())
    assert called == []
