"""Ophir Nova / Nova II power meter, through the StarLab COM component.

Needs ``pywin32`` and Ophir StarLab (it registers ``OphirLMMeasurement``). The
component is created when the driver is created, not at import.
"""

from __future__ import annotations

import time
from typing import Any

from flex.instrument import Instrument


def _dispatch() -> Any:
    import win32com.client

    return win32com.client.Dispatch("OphirLMMeasurement.CoLMMeasurement")


class OphirNova(Instrument):
    """The first meter found on USB, or the one with ``serial_number``."""

    def __init__(self, name: str = "power_meter", serial_number: str | None = None, **kwargs):
        super().__init__(name, **kwargs)
        self._com = _dispatch()
        self._com.StopAllStreams()
        self._com.CloseAll()
        devices = list(self._com.ScanUSB())
        if not devices:
            raise RuntimeError("No Ophir meter found on USB")
        serial = serial_number or devices[0]
        if serial not in devices:
            raise RuntimeError(f"Ophir meter {serial} not found (found: {', '.join(devices)})")
        self._handle = self._com.OpenUSBDevice(serial)
        if not self._com.IsSensorExists(self._handle, 0):
            raise RuntimeError(f"No sensor attached to Ophir meter {serial}")
        self._address = f"usb://{serial}"
        self.serial = serial
        self.add_parameter("power", getter=self.read_power, unit="W")

    def read_power(self, settle: float = 0.2) -> float:
        """Stream briefly and return the latest reading."""
        self._com.StartStream(self._handle, 0)
        time.sleep(settle)
        self._com.StopAllStreams()
        return self._com.GetData(self._handle, 0)[0][-1]

    def close(self) -> None:
        com, self._com = getattr(self, "_com", None), None
        if com is not None:
            com.StopAllStreams()
            com.CloseAll()
