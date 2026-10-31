"""The standard IF temperature and magnet commands shared by several apps, plus the
capability aliases (``get_field``/``set_field``)."""

from __future__ import annotations

from typing import Any


class IFTemperatureCommands:
    """Standard IF temperature commands (mix into a ``ZMQInstrument``)."""

    call: Any  # provided by ZMQInstrument

    def get_temperature_status(self, channel: int = 0) -> Any:
        """The full ``getTemperature`` reply, e.g. ``{"temperature": 5, "status": "Stable",
        "finished": True}`` on the PPMS."""
        return self.call("getTemperature", [channel])

    def get_temperature(self, channel: int = 0) -> Any:
        """Read the temperature of ``channel`` in kelvin."""
        reply = self.get_temperature_status(channel)
        return reply["temperature"] if isinstance(reply, dict) and "temperature" in reply else reply

    def set_temperature(
        self, setpoint: float, rate: float | None = None, *, channel: int = 0
    ) -> None:
        """Ramp ``channel`` to ``setpoint`` at ``rate`` (required by the app)."""
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

    # -- flex_drivers.levylab.capabilities.Magnet aliases -------------------------

    def get_field(self) -> Any:
        """The field in tesla: ``get_magnet`` with the ``{"field": ...}`` reply unwrapped."""
        reply = self.get_magnet()
        return reply["field"] if isinstance(reply, dict) and "field" in reply else reply

    def set_field(self, setpoint: float, *, rate: float | None = None) -> None:
        """Canonical capability alias for :meth:`set_magnet` (Z axis)."""
        if rate is None:
            raise ValueError(f"{type(self).__name__}.set_field requires a ramp rate")
        self.set_magnet(setpoint, rate)
