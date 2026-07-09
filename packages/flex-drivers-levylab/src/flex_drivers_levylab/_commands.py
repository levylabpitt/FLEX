"""Shared Instrument-Framework command mixins.

Port of FLEX v1 ``flex.inst.levylab.insttypes.Temperature`` and
``insttypes.Magnet``: the standard temperature / magnet JSON-RPC commands
that several LevyLab IF apps (PPMS, Opticool, Cryostation, Oxford magnet
controllers, Leiden TCs) share. The v2 mixins also provide the canonical
FLEX capability methods (``flex.instrument.capabilities.Temperature`` /
``Magnet``) as thin aliases so drivers conform structurally.
"""

from __future__ import annotations

from typing import Any


class IFTemperatureCommands:
    """Standard IF temperature commands (mix into a ``ZMQInstrument``)."""

    call: Any  # provided by ZMQInstrument

    def get_temperature(self, channel: int = 0) -> Any:
        """Read the temperature of ``channel`` (IF ``getTemperature``)."""
        return self.call("getTemperature", [channel])

    def set_temperature(
        self, setpoint: float, rate: float | None = None, *, channel: int = 0
    ) -> None:
        """Ramp ``channel`` to ``setpoint`` at ``rate`` (IF ``setTemperature``).

        ``rate`` may be passed positionally (v1 style) or as a keyword
        (capability style); the Instrument Framework requires it.
        """
        if rate is None:
            raise ValueError(f"{type(self).__name__}.set_temperature requires a ramp rate")
        self.call(
            "setTemperature",
            {"temperature": float(setpoint), "rate": float(rate), "channel": int(channel)},
        )

    def get_temperature_target(self, channel: int = 0) -> Any:
        """Read the temperature setpoint of ``channel`` (IF ``getTemperatureTarget``)."""
        return self.call("getTemperatureTarget", [channel])


class IFMagnetCommands:
    """Standard IF magnet commands (mix into a ``ZMQInstrument``)."""

    call: Any  # provided by ZMQInstrument

    def get_magnet(self) -> Any:
        """Read the magnetic field (IF ``getMagnet``)."""
        return self.call("getMagnet")

    def set_magnet(
        self, field: float, rate: float, axis: str = "Z", mode: str = "Persistent"
    ) -> None:
        """Ramp the field to ``field`` at ``rate`` (IF ``setMagnet``)."""
        self.call(
            "setMagnet",
            {"field": float(field), "rate": float(rate), "axis": axis, "mode": mode},
        )

    def get_magnet_target(self) -> Any:
        """Read the field setpoint (IF ``getMagnetTarget``)."""
        return self.call("getMagnetTarget", ["Z"])

    # -- flex.instrument.capabilities.Magnet aliases -------------------------

    def get_field(self) -> Any:
        """Canonical capability alias for :meth:`get_magnet`."""
        return self.get_magnet()

    def set_field(self, setpoint: float, *, rate: float | None = None) -> None:
        """Canonical capability alias for :meth:`set_magnet` (Z axis)."""
        if rate is None:
            raise ValueError(f"{type(self).__name__}.set_field requires a ramp rate")
        self.set_magnet(setpoint, rate)
