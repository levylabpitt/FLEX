"""Instrument capabilities.

Capabilities are structural protocols: a driver *conforms* by implementing the
methods — no inheritance required. Experiment code can then be written against
a capability instead of a concrete driver::

    magnet = exp.get(capabilities.Magnet)
    magnet.set_field(1.5)

``isinstance(driver, Temperature)`` works at runtime for any conforming class.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Temperature(Protocol):
    """Temperature controllers (cryostats, PPMS, Opticool, ...)."""

    def get_temperature(self) -> float: ...
    def set_temperature(self, setpoint: float, *, rate: float | None = None) -> None: ...


@runtime_checkable
class Magnet(Protocol):
    """Magnet power supplies / field controllers."""

    def get_field(self) -> float: ...
    def set_field(self, setpoint: float, *, rate: float | None = None) -> None: ...


@runtime_checkable
class DAQ(Protocol):
    """Multichannel analog I/O (lock-ins, DAQ cards, transport servers)."""

    def get_ai(self, channel: int) -> float: ...
    def set_ao(self, channel: int, value: float) -> None: ...


@runtime_checkable
class VSource(Protocol):
    """Voltage sources."""

    def get_voltage(self, channel: int) -> float: ...
    def set_voltage(self, channel: int, value: float) -> None: ...


@runtime_checkable
class Amplifier(Protocol):
    """Programmable amplifiers / preamps."""

    def get_gain(self, channel: int) -> float: ...
    def set_gain(self, channel: int, value: float) -> None: ...
