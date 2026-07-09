"""Sweeps and scans: autonomous measurement loops with minimal boilerplate.

::

    from flex import Scan, sweep

    Scan(sweep(gate, np.linspace(0, 1, 101), delay=0.1))\\
        .measure(lockin.x, lockin.y)\\
        .on_abort(lambda: gate(0))\\
        .run(exp, name="gate sweep")

Nested axes iterate as a grid (first axis outermost). Ctrl-C is safe: the data
file is finalized, the measurement is marked aborted, and cleanup callbacks
run before the interrupt propagates.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from math import prod
from typing import TYPE_CHECKING, Any

from flex.instrument import Parameter

if TYPE_CHECKING:
    from flex_exp.experiment import Experiment
    from flex_exp.measurement import Measurement


@dataclass
class SweepAxis:
    """One swept quantity: what to set, the values, and the pacing."""

    target: Parameter | Callable[[Any], None]
    values: Sequence[Any]
    delay: float = 0.0
    name: str = ""
    unit: str = ""
    before: Callable[[], None] | None = None  # called when this axis starts a pass
    after: Callable[[], None] | None = None  # called when a pass ends (also on abort)

    def __post_init__(self):
        self.values = list(self.values)
        if isinstance(self.target, Parameter):
            self.name = self.name or self.target.full_name
            self.unit = self.unit or self.target.unit
        elif not self.name:
            self.name = getattr(self.target, "__name__", "setpoint")

    def set(self, value: Any) -> None:
        if isinstance(self.target, Parameter):
            self.target.set(value)
        else:
            self.target(value)


def sweep(
    target: Parameter | Callable[[Any], None],
    values: Iterable[Any],
    *,
    delay: float = 0.0,
    name: str = "",
    unit: str = "",
    before: Callable[[], None] | None = None,
    after: Callable[[], None] | None = None,
) -> SweepAxis:
    """Describe a sweep of ``target`` (a Parameter or one-argument callable)
    over ``values``, waiting ``delay`` seconds after each set."""
    return SweepAxis(target, list(values), delay=delay, name=name, unit=unit, before=before, after=after)


@dataclass
class Scan:
    """Sweep one or more axes and measure at every point."""

    axes: tuple[SweepAxis, ...]
    _params: list[Parameter] = field(default_factory=list)
    _named: dict[str, Any] = field(default_factory=dict)
    _each: list[Callable[[dict], None]] = field(default_factory=list)
    _on_abort: list[Callable[[], None]] = field(default_factory=list)

    def __init__(self, *axes: SweepAxis):
        if not axes:
            raise ValueError("Scan needs at least one sweep axis")
        self.axes = axes
        self._params, self._named, self._each, self._on_abort = [], {}, [], []

    def measure(self, *parameters: Parameter, **named: Parameter | Callable[[], Any]) -> Scan:
        """What to record at every point (Parameters, or named callables)."""
        self._params.extend(parameters)
        self._named.update(named)
        return self

    def each(self, fn: Callable[[dict], None]) -> Scan:
        """Call ``fn(values)`` after every recorded point (live plots, checks)."""
        self._each.append(fn)
        return self

    def on_abort(self, fn: Callable[[], None]) -> Scan:
        """Cleanup to run if the scan is interrupted (e.g. ramp a gate to 0)."""
        self._on_abort.append(fn)
        return self

    def run(
        self,
        experiment: Experiment,
        *,
        name: str = "",
        notes: str = "",
        writer: str | None = None,
        progress: bool = True,
    ) -> Measurement:
        """Execute the scan inside a new measurement; returns it (finished)."""
        total = prod(len(axis.values) for axis in self.axes)
        with experiment.measurement(name or "scan", notes=notes, writer=writer) as m:
            for axis in self.axes:
                m.declare(axis.name, axis.unit)
            m.register(*self._params, **self._named)

            bar = None
            if progress:
                from tqdm.auto import tqdm

                bar = tqdm(total=total, desc=m.name, leave=False)
            try:
                self._run_axes(m, list(self.axes), {}, bar)
            except BaseException:  # noqa: B036 - KeyboardInterrupt must trigger cleanup too
                for fn in self._on_abort:
                    try:
                        fn()
                    except Exception as e:
                        experiment.log.error("on_abort callback failed: %s", e)
                raise
            finally:
                if bar is not None:
                    bar.close()
        return m

    def _run_axes(self, m: Measurement, axes: list[SweepAxis], setpoints: dict, bar) -> None:
        axis = axes[0]
        if axis.before is not None:
            axis.before()
        try:
            for value in axis.values:
                axis.set(value)
                if axis.delay:
                    time.sleep(axis.delay)
                point = {**setpoints, axis.name: value}
                if len(axes) == 1:
                    values = m.read_point(**point)
                    for fn in self._each:
                        fn(values)
                    if bar is not None:
                        bar.update(1)
                else:
                    self._run_axes(m, axes[1:], point, bar)
        finally:
            if axis.after is not None:
                axis.after()
