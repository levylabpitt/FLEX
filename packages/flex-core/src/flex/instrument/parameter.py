"""Parameters: named, unit-carrying get/set handles on instruments.

Parameters give sweeps and measurements a uniform way to address "things to
set and read" — with names and units recorded automatically in data files.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flex.instrument.base import Instrument


class Numbers:
    """Validate that a value is a number within [min, max]."""

    def __init__(self, min: float = -math.inf, max: float = math.inf):  # noqa: A002
        self.min, self.max = min, max

    def validate(self, value: Any) -> None:
        # numbers.Real admits numpy scalars (np.int64, np.float32) too
        if not isinstance(value, numbers.Real) or isinstance(value, bool):
            raise TypeError(f"expected a number, got {value!r}")
        if not (self.min <= value <= self.max):
            raise ValueError(f"{value} is outside [{self.min}, {self.max}]")

    def __repr__(self) -> str:
        return f"Numbers({self.min}, {self.max})"


class Enum:
    """Validate that a value is one of an allowed set."""

    def __init__(self, *values: Any):
        self.values = values

    def validate(self, value: Any) -> None:
        if value not in self.values:
            allowed = ", ".join(map(repr, self.values))
            raise ValueError(f"{value!r} is not one of: {allowed}")

    def __repr__(self) -> str:
        return f"Enum{self.values!r}"


class Parameter:
    """A named quantity of an instrument that can be read and/or written.

    Calling conventions::

        p()        # read
        p(value)   # write
        p.get() / p.set(value)
    """

    def __init__(
        self,
        name: str,
        *,
        instrument: Instrument | None = None,
        getter: Callable[[], Any] | None = None,
        setter: Callable[[Any], None] | None = None,
        unit: str = "",
        vals: Numbers | Enum | None = None,
        doc: str = "",
    ):
        self.name = name
        self.instrument = instrument
        self.unit = unit
        self.vals = vals
        self.__doc__ = doc or f"Parameter {name}" + (f" [{unit}]" if unit else "")
        self._getter = getter
        self._setter = setter

    @property
    def full_name(self) -> str:
        return f"{self.instrument.name}.{self.name}" if self.instrument else self.name

    @property
    def gettable(self) -> bool:
        return self._getter is not None

    @property
    def settable(self) -> bool:
        return self._setter is not None

    def get(self) -> Any:
        if self._getter is None:
            raise NotImplementedError(f"Parameter '{self.full_name}' is not readable")
        return self._getter()

    def set(self, value: Any) -> None:
        if self._setter is None:
            raise NotImplementedError(f"Parameter '{self.full_name}' is not writable")
        if self.vals is not None:
            self.vals.validate(value)
        self._setter(value)
        if self.instrument is not None:
            self.instrument.log.debug("%s = %r %s", self.name, value, self.unit)

    def __call__(self, *value: Any) -> Any:
        if not value:
            return self.get()
        if len(value) == 1:
            return self.set(value[0])
        raise TypeError(f"Parameter takes 0 (get) or 1 (set) arguments, got {len(value)}")

    def __repr__(self) -> str:
        unit = f", unit={self.unit!r}" if self.unit else ""
        return f"Parameter({self.full_name!r}{unit})"
