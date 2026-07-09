"""A hardware-free instrument for tests, docs, and dry runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flex.instrument.base import Instrument
from flex.instrument.parameter import Parameter


class SimulatedInstrument(Instrument):
    """Behaves like a text-protocol instrument, without hardware.

    ``replies`` maps a command to its response — either a fixed string or a
    callable receiving the full command. Unmatched queries are echoed back.
    Every command sent is recorded in :attr:`sent` for assertions in tests.

    For quick experiments, :meth:`add_sim_parameter` creates a settable,
    readable in-memory parameter::

        sim = SimulatedInstrument("sim")
        gate = sim.add_sim_parameter("gate", initial=0.0, unit="V")
        gate(0.5); gate()   # -> 0.5
    """

    def __init__(self, name: str = "sim", replies: dict[str, str | Callable[[str], str]] | None = None):
        super().__init__(name)
        self.replies = replies or {}
        self.sent: list[str] = []
        self.values: dict[str, Any] = {}
        self._address = "sim://" + name

    def write(self, cmd: str) -> None:
        self.sent.append(cmd)

    def query(self, cmd: str) -> str:
        self.sent.append(cmd)
        reply = self.replies.get(cmd, cmd)
        return reply(cmd) if callable(reply) else reply

    def idn(self) -> dict[str, str | None]:
        return {"vendor": "FLEX", "model": "SimulatedInstrument", "serial": self.name, "firmware": "0"}

    def add_sim_parameter(self, name: str, *, initial: Any = 0.0, unit: str = "", vals=None) -> Parameter:
        """An in-memory parameter backed by :attr:`values` (no protocol traffic)."""
        self.values[name] = initial
        return self.add_parameter(
            name,
            getter=lambda: self.values[name],
            setter=lambda v: self.values.__setitem__(name, v),
            unit=unit,
            vals=vals,
        )
