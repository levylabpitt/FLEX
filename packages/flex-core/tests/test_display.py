import sys
import types

from flex.display import auto_display, refresh_display


class Thing:
    def _repr_html_(self) -> str:
        return "<p>thing</p>"


def test_auto_display_noop_outside_interactive(monkeypatch):
    monkeypatch.setattr("flex.log.is_interactive", lambda: False)
    assert auto_display(Thing()) is None


def test_refresh_display_noop_without_id():
    refresh_display(Thing(), None)  # must not raise / must not touch IPython


def test_auto_display_and_refresh_when_interactive(monkeypatch):
    monkeypatch.setattr("flex.log.is_interactive", lambda: True)

    class Handle:
        display_id = "id-1"

    displayed, updated = [], []
    fake_display = types.ModuleType("IPython.display")
    fake_display.display = lambda html, display_id=None: displayed.append(html) or Handle()
    fake_display.update_display = lambda html, display_id: updated.append((html, display_id))
    fake_display.HTML = lambda s: s
    fake_ipython = types.ModuleType("IPython")
    fake_ipython.display = fake_display
    monkeypatch.setitem(sys.modules, "IPython", fake_ipython)
    monkeypatch.setitem(sys.modules, "IPython.display", fake_display)

    thing = Thing()
    display_id = auto_display(thing)
    assert display_id == "id-1"
    assert displayed == ["<p>thing</p>"]

    refresh_display(thing, display_id)
    assert updated == [("<p>thing</p>", "id-1")]
