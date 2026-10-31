"""Newport New Focus 8742 Picomotor controller, through the vendor USB library.

Needs ``pythonnet`` and the New Focus Picomotor application installed (it
supplies ``UsbDllWrap``). The library is loaded when the driver is created, not
at import. One instance drives one axis (1-4) of the first controller on USB.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from flex.instrument import Instrument

_DLL_DIR = Path("New Focus") / "New Focus Picomotor Application" / "Bin"


def _load_usb(dll_dir: Path | None = None) -> tuple[Any, Any]:
    import clr  # pythonnet

    folder = dll_dir or Path(os.environ["ProgramFiles"]) / _DLL_DIR
    if str(folder) not in sys.path:
        sys.path.append(str(folder))
    clr.AddReference("UsbDllWrap")
    from Newport.USBComm import USB
    from System.Text import StringBuilder

    return USB, StringBuilder


class NF8742(Instrument):
    """One axis of an 8742 controller."""

    def __init__(self, name: str = "picomotor", axis: int = 1, *, dll_dir: str | Path | None = None, **kwargs):
        if axis not in (1, 2, 3, 4):
            raise ValueError("Axis must be 1, 2, 3, or 4")
        super().__init__(name, **kwargs)
        self.axis = axis
        usb, self._builder = _load_usb(Path(dll_dir) if dll_dir else None)
        self._usb = usb(True)
        if not self._usb.OpenDevices(0, True):
            raise RuntimeError("Could not open USB devices")
        devices = self._usb.GetDeviceTable()
        if devices.Count == 0:
            self._usb.CloseDevices()
            raise RuntimeError("No 8742 controller found")
        enumerator = devices.GetEnumerator()
        enumerator.MoveNext()
        self._key = str(enumerator.Key)
        self._address = f"usb://{self._key}/{axis}"
        self.add_parameter("position", getter=self.get_position, setter=self.move_absolute)
        self.add_parameter("velocity", getter=self.get_velocity, setter=self.set_velocity, unit="steps/s")

    def _query(self, command: str) -> str:
        reply = self._builder(128)
        self._usb.Query(self._key, command, reply)
        return reply.ToString()

    def close(self) -> None:
        usb, self._usb = getattr(self, "_usb", None), None
        if usb is not None:
            usb.CloseDevices()

    def idn(self) -> dict[str, str | None]:
        return {"vendor": "Newport", "model": self._query("*IDN?"), "serial": None, "firmware": None}

    def reset(self) -> None:
        self._query("*RST")

    def get_position(self) -> int:
        return int(self._query(f"{self.axis}TP?"))

    def move_absolute(self, position: int) -> None:
        self._query(f"{self.axis}PA{int(position)}")

    def move_relative(self, steps: int) -> None:
        self._query(f"{self.axis}PR{int(steps)}")

    def move_direction(self, forward: bool = True) -> None:
        """Run continuously until :meth:`stop`."""
        self._query(f"{self.axis}MV{'+' if forward else '-'}")

    def stop(self) -> None:
        self._query(f"{self.axis}ST")

    def abort(self) -> None:
        self._query(f"{self.axis}AB")

    def get_velocity(self) -> int:
        return int(self._query(f"{self.axis}VA?"))

    def set_velocity(self, value: int) -> None:
        self._query(f"{self.axis}VA{int(value)}")

    def get_destination(self) -> int:
        return int(self._query(f"{self.axis}PA?"))

    def is_motion_done(self) -> bool:
        return self._query(f"{self.axis}MD?").strip() == "1"

    def get_error(self) -> str:
        """The controller's last error, as ``number, timestamp, message``."""
        return self._query("TB?")

    def get_motor_type(self) -> str:
        return self._query("QM?")

    def wait_until_done(self, timeout: float = 60.0, poll: float = 0.1) -> None:
        began = time.monotonic()
        while not self.is_motion_done():
            if time.monotonic() - began > timeout:
                raise TimeoutError(f"Axis {self.axis} still moving after {timeout:.0f} s")
            time.sleep(poll)

    def move_and_wait_absolute(self, position: int, timeout: float = 60.0) -> int:
        self.move_absolute(position)
        self.wait_until_done(timeout)
        return self.get_position()

    def move_and_wait_relative(self, steps: int, timeout: float = 60.0) -> int:
        self.move_relative(steps)
        self.wait_until_done(timeout)
        return self.get_position()
