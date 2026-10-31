"""Sphere Ultrafast Photonics d-scan, through the vendor ``dscan-library`` DLL.

The DLL comes with the d-scan software and is loaded when the driver is
created, not at import.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from flex.instrument import Instrument

_LIBRARY = Path("Sphere Ultrafast Photonics S.A") / "dscan-library" / "bin" / "dscan-library.dll"


class DScan(Instrument):
    """The d-scan with ``serial_number``; ``insertion`` is the glass wedge position in mm."""

    def __init__(self, name: str = "dscan", serial_number: str = "DM240913", *,
                 library: str | Path | None = None, **kwargs):
        super().__init__(name, **kwargs)
        path = Path(library) if library else Path(os.environ["ProgramFiles"]) / _LIBRARY
        self._lib = ctypes.cdll.LoadLibrary(str(path))
        self._invalid = self._lib.dscan_INVALID_HANDLE()
        self._handle = self._invalid
        handle = ctypes.c_uint32()
        self._check(self._lib.dscan_Create(serial_number.encode("utf-8"), ctypes.byref(handle)))
        self._handle = handle.value
        self._address = f"dscan://{serial_number}"
        self._check(self._lib.dscan_Connect(self._handle))
        self.add_parameter("insertion", getter=self.get_insertion, setter=self.set_insertion, unit="mm")

    def _check(self, status: int) -> None:
        if not status:
            return
        size = self._lib.dscan_ERROR_MESSAGE_BUFFER_LEN()
        message = ctypes.create_string_buffer(size)
        self._lib.dscan_GetLastStatusMessage(message, size)
        raise RuntimeError(message.value.decode("ascii").strip())

    def close(self) -> None:
        handle, self._handle = getattr(self, "_handle", None), None
        if handle is None or handle == self._invalid:
            return
        try:
            self._check(self._lib.dscan_Disconnect(handle))
        finally:
            self._check(self._lib.dscan_Destroy(handle))

    def is_connected(self) -> bool:
        return bool(self._lib.dscan_IsConnected(self._handle))

    def get_full_insertion_range(self) -> tuple[float, float]:
        start, stop = ctypes.c_double(), ctypes.c_double()
        self._check(self._lib.dscanComp_GetFullInsertionRange(self._handle, ctypes.byref(start), ctypes.byref(stop)))
        return start.value, stop.value

    def get_insertion(self) -> float:
        insertion = ctypes.c_double()
        self._check(self._lib.dscanComp_GetInsertion(self._handle, ctypes.byref(insertion)))
        return round(insertion.value, 3)

    def set_insertion(self, insertion_mm: float) -> None:
        self._check(self._lib.dscanComp_SetInsertion(self._handle, ctypes.c_double(insertion_mm)))
