import pytest

import flex_asana.hooks as hooks
from flex.ecosystem import FlexConfig
from flex_exp import Experiment


class FakeResponse:
    ok = True
    status_code = 200


@pytest.fixture
def posts(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return FakeResponse()

    monkeypatch.setattr(hooks.requests, "post", fake_post)
    return calls


def test_notify_from_config_and_events(posts, tmp_path):
    cfg = FlexConfig.model_validate(
        {
            "data": {"root": str(tmp_path)},
            "asana": {"webhook_url": "https://n8n.example.org/webhook/x"},
            "hooks": {"on_experiment_end": ["flex_asana.hooks:notify_n8n"]},
        }
    )
    with Experiment("jane", name="demo", config=cfg, cell_log=False):
        pass

    (call,) = posts
    url, body = call
    assert url == "https://n8n.example.org/webhook/x"
    assert body["event"] == "experiment.end"
    assert body["user"] == "jane"
    assert body["end_time"] is not None


def test_no_webhook_is_silent(posts, monkeypatch):
    monkeypatch.delenv("FLEX_N8N_WEBHOOK", raising=False)
    hooks.notify_n8n("experiment.start", None)  # must not raise
    assert posts == []


def test_env_fallback(posts, monkeypatch):
    monkeypatch.setenv("FLEX_N8N_WEBHOOK", "https://n8n.example.org/webhook/env")
    hooks.notify_n8n("experiment.start", None)
    assert posts[0][0].endswith("/env")


def test_network_failure_is_swallowed(monkeypatch):
    def boom(url, json=None, timeout=None):
        raise hooks.requests.ConnectionError("down")

    monkeypatch.setattr(hooks.requests, "post", boom)
    monkeypatch.setenv("FLEX_N8N_WEBHOOK", "https://n8n.example.org/webhook/x")
    hooks.notify_n8n("experiment.end", None)  # must not raise
