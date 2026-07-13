from dataclasses import dataclass
from datetime import datetime

import pytest

from flex_asana.comms import AsanaComms


@dataclass
class FakeExperiment:
    id: str
    user: str
    start_time: datetime
    end_time: datetime | None = None


@pytest.fixture
def comms(monkeypatch):
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("ASANA_WORKSPACE_GID", "ws1")
    monkeypatch.setenv("ASANA_EXPERIMENTS_PROJECT_GID", "proj1")
    return AsanaComms()


def test_notify_start_creates_task_and_returns_gid(comms, monkeypatch):
    monkeypatch.setattr(comms._sync.client, "get_project_custom_field_specs", lambda gid: {})
    monkeypatch.setattr(comms._sync.client, "list_users", lambda ws: [{"email": "jane@lab.org", "gid": "u1"}])
    captured = {}
    monkeypatch.setattr(
        comms._sync.client, "create_task",
        lambda project_gid, name, **kw: captured.update(project_gid=project_gid, name=name, **kw)
        or {"gid": "task1"},
    )
    exp = FakeExperiment(id="20260713-abcd", user="jane", start_time=datetime(2026, 7, 13, 9, 0, 0))

    state = comms.notify_start(exp)

    assert state == "task1"
    assert captured["project_gid"] == "proj1"
    assert "20260713-abcd" in captured["name"]
    assert "jane" in captured["name"]


def test_notify_end_updates_task(comms, monkeypatch):
    monkeypatch.setattr(
        comms._sync.client, "get_project_custom_field_specs",
        lambda gid: {"End Time": {"gid": "f2", "type": "text"}},
    )
    captured = {}
    monkeypatch.setattr(
        comms._sync.client, "update_task", lambda task_gid, **kw: captured.update(task_gid=task_gid, **kw)
    )
    exp = FakeExperiment(
        id="x", user="jane", start_time=datetime.now(), end_time=datetime(2026, 7, 13, 17, 0, 0)
    )

    comms.notify_end(exp, "task1")
    assert captured["task_gid"] == "task1"


def test_notify_end_noop_with_no_state(comms, monkeypatch):
    called = []
    monkeypatch.setattr(comms._sync.client, "update_task", lambda *a, **k: called.append(1))
    exp = FakeExperiment(id="x", user="jane", start_time=datetime.now(), end_time=datetime.now())

    comms.notify_end(exp, None)
    assert called == []
