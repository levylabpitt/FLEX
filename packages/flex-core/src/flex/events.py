"""FLEX event bus.

A deliberately small synchronous pub/sub used to attach hooks (notifications,
lab bookkeeping) to the experiment lifecycle. Subscriber errors are logged and
swallowed: a broken webhook must never break a running experiment.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from flex.log import get_logger

EVENTS = (
    "experiment.start",
    "experiment.end",
    "measurement.start",
    "measurement.end",
    "measurement.abort",
    "note.added",
    "instrument.added",
)


@dataclass
class EventBus:
    _subscribers: dict[str, list[tuple[str, Callable[..., None]]]] = field(default_factory=dict)

    def subscribe(self, event: str, fn: Callable[..., None], *, name: str = "") -> None:
        """Register ``fn`` to be called on ``event``. ``name`` is used in error logs."""
        self._check(event)
        self._subscribers.setdefault(event, []).append((name or getattr(fn, "__name__", "hook"), fn))

    def unsubscribe(self, event: str, fn: Callable[..., None]) -> None:
        self._check(event)
        subs = self._subscribers.get(event, [])
        self._subscribers[event] = [(n, f) for n, f in subs if f is not fn]

    def emit(self, event: str, **payload) -> None:
        """Call every subscriber of ``event``; errors are logged, never raised."""
        self._check(event)
        for name, fn in self._subscribers.get(event, []):
            try:
                fn(event=event, **payload)
            except Exception:
                get_logger("events").exception("Hook '%s' failed on %s (ignored)", name, event)

    @staticmethod
    def _check(event: str) -> None:
        if event not in EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid events: {', '.join(EVENTS)}")
