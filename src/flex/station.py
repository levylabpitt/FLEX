"""flex-afm's own Station and ``flex.toml`` loader.

**This is not FLEX's.** FLEX v1 (``flex==1.0.5``, the lab's stable ``main``)
has no ``Station``, no config file, no driver registry and no ``flex`` CLI: a
v1 script constructs each driver by hand with its address. That is fine for a
notebook and useless for "the bench, from one file", which is what
``examples/flex.toml`` describes and what ``runners/`` and
``scripts/write_and_watch.py`` build from.

So this module keeps the *file format* the repo already ships and supplies the
loader underneath it. Nothing about the format changed with the move to v1
except which ``driver`` strings the lock-in and Krohn-Hite stanzas name (see
:data:`ALIASES`); ``[instruments.afm]`` is byte-for-byte what it was.

::

    from flex_afm.station import Station

    station = Station.load("examples/flex.toml")
    print(station.afm.get_state())
    station.close()

The loader is deliberately thin: ``tomllib`` + ``importlib``, one instrument
per ``[instruments.<name>]`` table, and a failure builds *no* instrument rather
than taking the bench down -- a station with an unplugged lock-in must still
give you the AFM, so failures land in :attr:`Station.failed` and the rest load.
That promise needs one piece of care: a FLEX v1 driver constructed against a
dead endpoint does not fail, it **hangs the load forever**, so the loader ACKs
the endpoint itself first. See :meth:`InstrumentConfig._preflight`.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import tomllib
from pathlib import Path
from typing import Any

CATALOG = {'levylab.afm_litho': 'flex.inst.levylab.afm_litho:AFMLitho'}
from flex.inst.base import Instrument

__all__ = ["ALIASES", "InstrumentConfig", "Station", "resolve_driver"]

_log = logging.getLogger("flex_afm.station")

#: Short driver names accepted in a ``driver = ...`` field, on top of any
#: ``"module:Class"`` reference. The two LevyLab entries name **FLEX v1's own**
#: driver classes; the AFM entry comes from :data:`flex_afm.CATALOG`.
ALIASES: dict[str, str] = {
    **CATALOG,
    "levylab.lockin": "flex.inst.levylab.Lockin:Lockin",
    "levylab.krohn_hite": "flex.inst.levylab.Krohn_Hite_7008:Krohn_Hite_7008",
}

#: Keys of an ``[instruments.<name>]`` table the loader consumes itself; every
#: other key is passed to the driver as a keyword argument.
RESERVED_KEYS = frozenset({"driver", "address", "log", "log_interval"})

#: Seconds a FLEX v1 driver's endpoint gets to answer the loader's own ACK
#: before that instrument is recorded as failed. Short on purpose: this is a
#: liveness probe, not the instrument's timeout (which the station file still
#: sets), and every instrument in the file pays it in series when the bench is
#: half up.
PREFLIGHT_TIMEOUT = 1.0


def resolve_driver(ref: str) -> type:
    """``"module:Class"`` (or an :data:`ALIASES` short name) -> the class.

    FLEX v3 had ``flex.components.resolve_driver`` for this; v1 has nothing,
    so it is 6 lines of :mod:`importlib` here.
    """
    target = ALIASES.get(ref, ref)
    if ":" not in target:
        raise ValueError(
            f"driver {ref!r} is neither a 'module:Class' reference nor one of the "
            f"known short names ({', '.join(sorted(ALIASES))})"
        )
    module_name, _, class_name = target.partition(":")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ImportError(f"{module_name!r} has no {class_name!r}") from e


class InstrumentConfig:
    """One ``[instruments.<name>]`` table, and how to build it."""

    def __init__(self, driver: str, address: str | None = None, **kwargs: Any):
        self.driver = driver
        self.address = address
        self.kwargs = kwargs

    def build(self, name: str, *, preflight_timeout: float = PREFLIGHT_TIMEOUT) -> Any:
        """Construct the driver, adapting to the two constructor shapes in play.

        This repo's own drivers take ``(name, address, **kwargs)``. FLEX v1's
        take a **single positional address** and nothing else --
        ``Lockin(address='tcp://...')``, no name, no timeout -- so a
        ``timeout`` in the station file cannot go through their ``__init__``
        at all. It is applied afterwards through v1's socket-wide
        ``_set_zmq_timeout()``, which is the only timeout v1 has.

        **A v1 driver is never constructed against an endpoint that has not
        answered first.** See :meth:`_preflight`: constructing one against a
        dead address does not raise and move on, it hangs the whole load
        forever.
        """
        cls = resolve_driver(self.driver)
        if not issubclass(cls, Instrument) and self.address:
            self._preflight(name, preflight_timeout)
        kwargs = dict(self.kwargs)
        parameters = inspect.signature(cls).parameters
        takes_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())

        if issubclass(cls, Instrument) or "name" in parameters:
            instrument = cls(name, self.address, **self._accepted(kwargs, parameters, takes_kwargs))
            leftover: dict[str, Any] = {}
        else:  # a FLEX v1 driver: one positional address
            accepted = self._accepted(kwargs, parameters, takes_kwargs)
            leftover = {k: v for k, v in kwargs.items() if k not in accepted}
            instrument = cls(self.address, **accepted)

        timeout = leftover.get("timeout")
        if timeout is not None and hasattr(instrument, "_set_zmq_timeout"):
            instrument._set_zmq_timeout(float(timeout))
        return instrument

    def _preflight(self, name: str, timeout: float) -> None:
        """Prove the endpoint answers, *before* a FLEX v1 driver is built on it.

        v1's ``Instrument.__init__`` (``flex/inst/base.py``) opens a socket on
        its own ``zmq.Context``, sends an ACK, and on failure closes only the
        socket -- at the default ``LINGER = -1``, with the ACK still
        undelivered -- and never terms the context. The half-built instrument
        is then dropped, and the orphan ``Context`` is collected at whatever
        later statement happens to trigger a GC pass; ``Context.__del__`` calls
        ``term()``, which blocks on that undeliverable ACK **forever**. The
        symptom is not a slow load, it is ``Station.load`` never returning, and
        it takes the rest of the bench with it: with the lock-in or the
        Krohn-Hite down, ``flex_probe.py --station`` printed no table at all
        and ``write_and_watch.py`` hung before it reached the AFM.

        So the loader asks first, over a :class:`~flex_afm._link.JsonRpcLink`
        -- its own context, ``LINGER 0``, one ACK, a short timeout, closed
        immediately either way, which is exactly the teardown v1 does not do.
        A silent endpoint raises here, and :meth:`Station.load` records the
        instrument in :attr:`Station.failed` without the v1 class ever being
        constructed. Drivers that *are* ours skip this: their own
        ``connect_check`` ACK is the same probe and cleans up after itself.
        """
        try:
            Instrument(f"{name}-preflight", self.address, timeout=timeout).close()
        except Exception as e:  # noqa: BLE001 - re-raised as a clear one
            raise ConnectionError(
                f"{self.address} did not answer ACK within {timeout:g}s "
                f"({type(e).__name__}) -- is the instrument's app running?"
            ) from e

    @staticmethod
    def _accepted(kwargs: dict[str, Any], parameters: Any, takes_kwargs: bool) -> dict[str, Any]:
        if takes_kwargs:
            return dict(kwargs)
        return {k: v for k, v in kwargs.items() if k in parameters}

    def __repr__(self) -> str:
        return f"InstrumentConfig({self.driver!r}, {self.address!r})"


class Station:
    """A named collection of instruments, addressed by name or attribute."""

    def __init__(self, instruments: dict[str, Any] | None = None, *,
                 name: str = "", config_path: Path | None = None):
        self.name = name or "flex-afm"
        self.config_path = config_path
        self.instruments: dict[str, Any] = dict(instruments or {})
        #: name -> error message, for entries :meth:`load` could not build
        #: (an unplugged instrument, a bad driver reference, a dead socket).
        self.failed: dict[str, str] = {}

    @classmethod
    def load(cls, path: str | Path, *names: str) -> Station:
        """Build a Station from a ``flex.toml`` (all instruments, or just
        ``names``). One instrument failing to build never stops the others."""
        config_path = Path(path)
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)

        configured: dict[str, InstrumentConfig] = {}
        for inst_name, table in (data.get("instruments") or {}).items():
            if not isinstance(table, dict) or "driver" not in table:
                raise ValueError(f"[instruments.{inst_name}] has no driver = \"module:Class\"")
            kwargs = {k: v for k, v in table.items() if k not in RESERVED_KEYS}
            configured[inst_name] = InstrumentConfig(
                table["driver"], table.get("address"), **kwargs
            )
        if not configured:
            raise ValueError(f"No [instruments.*] defined in {config_path}")
        unknown = [n for n in names if n not in configured]
        if unknown:
            raise KeyError(
                f"Not in the configuration: {', '.join(unknown)} "
                f"(configured: {', '.join(configured)})"
            )

        station = cls(name=(data.get("lab") or {}).get("station") or "",
                      config_path=config_path)
        for inst_name in names or tuple(configured):
            try:
                station.instruments[inst_name] = configured[inst_name].build(inst_name)
            except Exception as e:  # noqa: BLE001 - one bad instrument, not the bench
                station.failed[inst_name] = f"{type(e).__name__}: {e}"
        return station

    def add_instrument(self, instrument: Any, name: str | None = None) -> Any:
        name = name or getattr(instrument, "name", None)
        if not name:
            raise ValueError("an instrument needs a name")
        if name in self.instruments:
            raise ValueError(f"Station already has an instrument {name!r}")
        self.instruments[name] = instrument
        return instrument

    def get(self, name: str) -> Any:
        if name not in self.instruments:
            have = ", ".join(self.instruments) or "none"
            raise KeyError(f"No instrument {name!r} (loaded: {have})")
        return self.instruments[name]

    def snapshot(self, *, read: bool = False) -> dict[str, Any]:
        return {name: inst.snapshot(read=read) for name, inst in self.instruments.items()
                if hasattr(inst, "snapshot")}

    def close(self) -> None:
        for name, inst in self.instruments.items():
            try:
                inst.close()
            except Exception as e:  # noqa: BLE001 - closing the bench never raises
                _log.warning("%s.close() failed: %s", name, e)

    def __getattr__(self, name: str) -> Any:
        instruments = self.__dict__.get("instruments", {})
        if name in instruments:
            return instruments[name]
        raise AttributeError(f"Station has no attribute or instrument {name!r}")

    def __dir__(self) -> list[str]:
        return [*super().__dir__(), *self.__dict__.get("instruments", {})]

    def __enter__(self) -> Station:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<Station {self.name!r}: {', '.join(self.instruments) or 'empty'}>"
