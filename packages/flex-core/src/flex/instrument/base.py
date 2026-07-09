"""The protocol-independent instrument base class."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flex.instrument.parameter import Enum, Numbers, Parameter
from flex.log import get_logger


class Instrument:
    """Base class for every FLEX instrument driver.

    Holds everything that does not depend on how the instrument is connected:
    name, logging, the parameter registry, snapshots, and context-manager
    lifecycle. Protocol base classes in ``flex-protocols`` add the connection
    (``VISAInstrument.query``, ``ZMQInstrument.call``, ...).
    """

    def __init__(self, name: str, *, metadata: dict[str, Any] | None = None):
        self.name = name
        self.metadata = metadata or {}
        self.log = get_logger(f"inst.{name}")
        self.parameters: dict[str, Parameter] = {}

    # -- connection interface (protocol classes override what they support) --

    @property
    def address(self) -> str:
        return getattr(self, "_address", "")

    def idn(self) -> dict[str, str | None]:
        """Identification info. Protocol classes query the instrument."""
        return {"vendor": None, "model": type(self).__name__, "serial": None, "firmware": None}

    def close(self) -> None:
        """Release the connection. Safe to call more than once."""

    # -- parameters -----------------------------------------------------------

    def add_parameter(
        self,
        name: str,
        *,
        get_cmd: str | None = None,
        set_cmd: str | None = None,
        getter: Callable[[], Any] | None = None,
        setter: Callable[[Any], None] | None = None,
        get_parser: Callable[[str], Any] | None = None,
        unit: str = "",
        vals: Numbers | Enum | None = None,
        doc: str = "",
    ) -> Parameter:
        """Register a parameter, from command strings or Python callables.

        ``get_cmd``/``set_cmd`` are command templates sent through the
        instrument's ``query``/``write`` (``set_cmd`` is formatted with the
        value, e.g. ``"SOUR:VOLT {}"``). ``getter``/``setter`` are arbitrary
        callables for instruments whose methods already exist.
        """
        if name in self.parameters:
            raise ValueError(f"{self.name} already has a parameter '{name}'")

        if get_cmd is not None:
            if getter is not None:
                raise ValueError("give either get_cmd or getter, not both")
            query = getattr(self, "query", None)
            if not callable(query):
                raise TypeError(f"{type(self).__name__} has no query(); use getter= instead")
            parser = get_parser or (lambda s: s)

            def getter() -> Any:
                return parser(query(get_cmd))

        if set_cmd is not None:
            if setter is not None:
                raise ValueError("give either set_cmd or setter, not both")
            write = getattr(self, "write", None)
            if not callable(write):
                raise TypeError(f"{type(self).__name__} has no write(); use setter= instead")

            def setter(value: Any) -> None:
                write(set_cmd.format(value))

        parameter = Parameter(
            name, instrument=self, getter=getter, setter=setter, unit=unit, vals=vals, doc=doc
        )
        self.parameters[name] = parameter
        return parameter

    # -- snapshot -----------------------------------------------------------

    def snapshot(self, *, read: bool = True) -> dict[str, Any]:
        """A JSON-friendly description of this instrument and (best-effort)
        its current parameter values."""
        params: dict[str, Any] = {}
        for name, p in self.parameters.items():
            entry: dict[str, Any] = {"unit": p.unit}
            if read and p.gettable:
                try:
                    entry["value"] = p.get()
                except Exception as e:
                    entry["error"] = str(e)
            params[name] = entry
        return {
            "name": self.name,
            "class": f"{type(self).__module__}.{type(self).__qualname__}",
            "address": self.address,
            "parameters": params,
            "metadata": self.metadata,
        }

    # -- lifecycle / display -------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        address = f" @ {self.address}" if self.address else ""
        return f"<{type(self).__name__} '{self.name}'{address}>"

    def _repr_html_(self) -> str:
        from flex.display import instrument_html

        return instrument_html(self)
