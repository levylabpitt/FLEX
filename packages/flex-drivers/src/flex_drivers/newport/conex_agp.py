"""Newport CONEX-AGP piezo mirror mount, through Newport's .NET command library.

Needs ``pythonnet`` (``flex-drivers[windows]``) and the Newport CONEX-AGP applet installed (it supplies
``ConexAGPCmdLib.DLL``). The library is loaded when the driver is created, not
at import.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from flex.instrument import Instrument

_DLL_DIR = Path("Newport") / "Piezo Motion Control" / "Newport CONEX-AGP Applet" / "Bin"


def _load_commands(dll_dir: Path | None = None) -> Any:
    import clr  # pythonnet

    folder = dll_dir or Path(os.environ["ProgramFiles"]) / _DLL_DIR
    if str(folder) not in sys.path:
        sys.path.append(str(folder))
    clr.AddReference(str(folder / "ConexAGPCmdLib.DLL"))
    from Newport.ConexAGPCmdLib import ConexAGPCmds

    return ConexAGPCmds


class ConexAGP(Instrument):
    """CONEX-AGP on a serial port. ``addr`` is the controller's bus address."""

    def __init__(self, name: str = "conex", port: str = "COM8", addr: int = 1, *,
                 dll_dir: str | Path | None = None, **kwargs):
        super().__init__(name, **kwargs)
        self._address = port
        self.addr = addr
        self._ctl = _load_commands(Path(dll_dir) if dll_dir else None)()
        if self._ctl.OpenInstrument(port) != 0:
            raise ConnectionError(f"Could not open the CONEX-AGP on {port}")
        self.add_parameter("position", getter=self.get_position, setter=self.move_absolute)

    def _cmd(self, command: str, *args: Any) -> tuple:
        """Run one library command; the library returns ``(status, *outputs)``."""
        result = getattr(self._ctl, command)(self.addr, *args)
        result = result if isinstance(result, tuple) else (result,)
        if result[0] != 0:
            raise RuntimeError(f"CONEX-AGP {command} failed ({result[-1]})")
        return result[1:]

    def close(self) -> None:
        ctl, self._ctl = getattr(self, "_ctl", None), None
        if ctl is not None and ctl.CloseInstrument() != 0:
            raise ConnectionError("Could not close the CONEX-AGP")

    def get_version(self) -> str:
        return self._cmd("VE")[0]

    def get_position(self) -> float:
        return self._cmd("TP")[0]

    def move_absolute(self, position: float) -> None:
        self._cmd("PA_Set", position)

    def move_relative(self, delta: float) -> None:
        self._cmd("PR_Set", delta)

    def stop(self) -> None:
        self._cmd("ST")

    def home(self) -> None:
        self._cmd("OR", "")

    def get_status(self) -> dict[str, str]:
        error_code, state, error = self._cmd("TS", "", "", "")
        return {"error_code": error_code, "state": state, "error": error}
