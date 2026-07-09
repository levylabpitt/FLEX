"""LevyLab Transport Server driver.

<https://github.com/levylabpitt/Transport>

Port of FLEX v1 ``flex.inst.levylab.TransportServer`` (author: Pubudu
Wijesinghe <pubudu.wijesinghe@levylab.org>). The v1 class was named
``Transport``; v2 renames it to ``TransportServer`` (registry name
``levylab.transport_server``). v1 defined no ``_LABVIEW_CLASS_NAME`` for this
app, so :attr:`TransportServer.lv_class` is ``None``.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from flex_protocols import ZMQInstrument

_ALLOWED_VIS = {"LockinSweep", "LockinTime", "LockinTimeDelay"}


class TransportServer(ZMQInstrument):
    """Transport measurement orchestration server (LevyLab IF app)."""

    lv_class: str | None = None  # v1 defined no _LABVIEW_CLASS_NAME for this app

    def __init__(self, name: str = "transport", address: str = "tcp://localhost:15260", **kwargs):
        super().__init__(name, address, **kwargs)

    def start_transport(self, vi: Literal["LockinTime", "LockinSweep", "LockinTimeDelay"]) -> Any:
        """Start a transport VI (IF ``startTransport``).

        Raises:
            ValueError: If ``vi`` is not one of the allowed VI names.
        """
        if vi not in _ALLOWED_VIS:
            raise ValueError(f"Invalid value: {vi}. Allowed values are: {', '.join(_ALLOWED_VIS)}")
        return self.call("startTransport", {"method": vi})

    def stop_transport(self) -> Any:
        return self.call("stopTransport", {})

    def get_status(self) -> str:
        return self.call("getStatus", {})["Status"]

    def set_expt_folder(self, folder: str) -> None:
        self.call("setExptFolder", {"folder": folder})

    def get_expt_folder(self) -> str:
        return self.call("getExptFolder", {})["folder"]

    def set_expt_comments(self, comments: str) -> None:
        self.call("setExptComments", {"comments": comments})

    def get_expt_comments(self) -> str:
        return self.call("getExptComments", {})["comments"]

    def set_expt_param(
        self, param: str, value: str | int | float | list[str] | list[int] | list[float]
    ) -> None:
        """Set one experiment parameter (IF ``setExptParam``).

        Raises:
            TypeError: If ``value`` is not a str/int/float or a homogeneous
                list thereof.
        """
        if isinstance(value, str | int | float):
            pass
        elif isinstance(value, list):
            if not value:
                pass
            elif all(isinstance(v, str) for v in value):
                pass
            elif all(isinstance(v, int) for v in value):
                pass
            elif all(isinstance(v, float) for v in value):
                pass
            else:
                raise TypeError(f"List for '{param}' must contain only str, int, or float.")
        else:
            raise TypeError(f"Value for '{param}' must be str, int, float, or list thereof.")

        self.call("setExptParam", {param: value})

    def set_refresh_time(self, refresh_time: float) -> None:
        """Set the data refresh time in milliseconds (IF ``setRefreshTime``)."""
        self.call("setRefreshTime", {"Refresh Time (ms)": refresh_time})

    def set_sweep_config(self, sweep_config: dict) -> None:
        self.call("setSweepConfig", sweep_config)

    def get_sweep_config(self) -> Any:
        return self.call("getSweepConfig", {})

    # -- custom functions -----------------------------------------------------

    def lockin_sweep(
        self,
        expt_folder: str,
        expt_comments: str,
        sweep_config: dict,
        run_continuous: bool = False,
    ) -> None:
        """Perform a lock-in sweep with the specified configuration.

        Port of the v1 ``LockinSweep`` helper.
        """
        self.set_sweep_config(sweep_config)
        self.set_expt_folder(expt_folder)
        self.set_expt_comments(expt_comments)

        self.start_transport("LockinSweep")
        time.sleep(2)  # Allow some time for the transport to start
        if run_continuous:
            self.log.info("Continuous Sweep Running Asynchronously...")
            return
        self.stop_transport()
        while self.get_status() != "idle":
            time.sleep(1)
        self.log.info("Sweep Ended.")

    def get_expt_details(self) -> tuple[str, str]:
        """Return ``(experiment folder, experiment comments)``."""
        return self.get_expt_folder(), self.get_expt_comments()
