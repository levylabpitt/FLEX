import pytest

from flex.events import EventBus


def test_subscribe_emit():
    bus = EventBus()
    seen = []
    bus.subscribe("experiment.start", lambda event, **kw: seen.append((event, kw)))
    bus.emit("experiment.start", experiment="e1")
    assert seen == [("experiment.start", {"experiment": "e1"})]


def test_subscriber_errors_are_isolated():
    bus = EventBus()
    seen = []

    def broken(event, **kw):
        raise RuntimeError("webhook down")

    bus.subscribe("experiment.end", broken)
    bus.subscribe("experiment.end", lambda event, **kw: seen.append(event))
    bus.emit("experiment.end")  # must not raise
    assert seen == ["experiment.end"]


def test_unknown_event_rejected():
    bus = EventBus()
    with pytest.raises(ValueError, match="Unknown event"):
        bus.subscribe("experiment.explode", print)
    with pytest.raises(ValueError, match="Unknown event"):
        bus.emit("experiment.explode")


def test_unsubscribe():
    bus = EventBus()
    seen = []

    def hook(event, **kw):
        seen.append(event)

    bus.subscribe("note.added", hook)
    bus.unsubscribe("note.added", hook)
    bus.emit("note.added")
    assert seen == []
