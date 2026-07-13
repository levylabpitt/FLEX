"""CESession: a FLEX experiment bootstrapped from the LevyLab
*Configure Experiments* VI.

The VI writes ``%LOCALAPPDATA%/Levylab/Control Experiment/Control
Experiment.json`` describing the wiring, device folder, and connected
Instrument-Framework apps. ``CESession`` reads it, connects a driver to every
configured instrument (matched by LabVIEW class name), and is otherwise a
normal :class:`~flex_exp.experiment.Experiment` — measurements, scans, notes,
and hooks all work the same.

Usage::

    from flex import CESession

    with CESession() as exp:
        exp.DAQ.set_ao_dc(1, 0.5)      # instruments attach by their CE "Type"
        ...

Requires the ``flex-drivers`` package (``flex install flex-drivers``),
activated by the ``levylab`` ecosystem.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from flex.components import load_ref
from flex_exp.experiment import Experiment

_CE_CONFIG = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Levylab"
    / "Control Experiment"
    / "Control Experiment.json"
)


@dataclass
class CEInfo:
    """Parsed contents of the Configure Experiments file."""

    user: str = "Unknown"
    device: str = "Unknown"
    device_path: str = ""
    description: str = ""
    station: str = "Unknown"
    instruments: list[dict] = field(default_factory=list)
    wiring: dict[int, tuple[str, str]] = field(default_factory=dict)
    timestamp: datetime | None = None


def parse_ce_config(raw: dict) -> CEInfo:
    """Parse the Configure Experiments JSON (same rules as FLEX v1)."""
    exp = raw.get("Experiment", {})
    meta: dict = {}
    if "json" in raw:
        try:
            meta = json.loads(raw["json"])
        except (json.JSONDecodeError, TypeError):
            pass
    device_meta = meta.get("Device", {})

    instruments = []
    for inst in exp.get("Instruments", []):
        class_path = inst.get("class path", "")
        # generic stubs from the instrument-types folder are not connections
        if "levylab/instrument framework/instrument types" in class_path.replace("\\", "/").lower():
            continue
        instruments.append(
            {
                "Type": inst.get("Type", "Unknown"),
                "Address": inst.get("Address", ""),
                "LVClass": Path(class_path).name if class_path else "",
                "FlexClass": None,  # filled in as drivers connect
            }
        )

    wiring_config = raw.get("Wiring Configuration", {})
    wiring = {
        channel: (electrode, label)
        for channel, electrode, label in zip(
            wiring_config.get("Lockin Ch", []),
            wiring_config.get("KH", {}).get("Electrodes", []),
            wiring_config.get("KH", {}).get("Labels", []),
            strict=False,
        )
        if electrode
    }

    try:
        timestamp = datetime.fromisoformat(device_meta.get("Time", "")[:19])
    except (ValueError, TypeError):
        timestamp = None

    return CEInfo(
        user=exp.get("User", device_meta.get("User", "Unknown")),
        device=exp.get("Device", device_meta.get("Device", "Unknown")),
        device_path=exp.get("Device Path", ""),
        description=exp.get("Device Description", ""),
        station=exp.get("Instrument", "Unknown"),
        instruments=instruments,
        wiring=wiring,
        timestamp=timestamp,
    )


class CESession(Experiment):
    """An Experiment whose instruments come from the Configure Experiments VI.

    Args:
        user: Override the user recorded in the CE file.
        ce_path: Override the CE JSON location.
        timeout: Seconds before a slow initialization prints a warning.
        transport_server: Also connect the (implicit) Transport server app.
        driver_registry: Override the LabVIEW-class -> driver mapping
            (defaults to the flex_drivers.levylab registry).
        verbose: Print a line as each instrument connects. In a terminal this
            is on top of the usual logging; in Jupyter/VS Code Interactive
            (where routine logging is quieted to avoid cluttering the cell,
            see flex.log.enable_console) it's the only per-instrument
            progress you'll see, alongside the live-updating summary card
            (from Experiment's flex.display.auto_display) every instrument
            connect refreshes.
    """

    def __init__(
        self,
        user: str = "",
        *,
        ce_path: str | Path | None = None,
        timeout: float = 10.0,
        transport_server: bool = True,
        driver_registry: dict[str, str] | None = None,
        verbose: bool = False,
        **kwargs: Any,
    ):
        self._ce_path = Path(ce_path) if ce_path else _CE_CONFIG
        self.ce = parse_ce_config(self._load_ce())
        self._registry = driver_registry if driver_registry is not None else _levylab_registry()
        self.verbose = verbose

        super().__init__(user or self.ce.user, name=kwargs.pop("name", self.ce.device), **kwargs)

        watchdog = threading.Timer(timeout, self._slow_init_warning, [timeout])
        watchdog.start()
        try:
            if transport_server:
                self._connect_transport_server()
            self._connect_instruments(self.ce.instruments)
        except BaseException:
            self.close_all()
            self.end()
            raise
        finally:
            watchdog.cancel()

    # -- public API (v1-compatible) ------------------------------------------

    @property
    def wiring(self) -> dict[int, tuple[str, str]]:
        """{lockin channel: (electrode, label)}"""
        return self.ce.wiring

    def get_device_path(self) -> Path:
        """The device folder chosen in the VI (for extra file saving)."""
        return Path(self.ce.device_path)

    def update(self) -> None:
        """Reload the CE file and connect any newly added instruments."""
        previous = {i["Type"]: i["FlexClass"] for i in self.ce.instruments}
        self.ce = parse_ce_config(self._load_ce())
        new = []
        for inst in self.ce.instruments:
            if inst["Type"] in self.instruments:
                inst["FlexClass"] = previous.get(inst["Type"])
            else:
                new.append(inst)
        if new:
            self._connect_instruments(new)
            self.log.info("New instruments: %s", ", ".join(i["Type"] for i in new))
        else:
            self.log.info("Session refreshed; no new instruments")

    # -- internals ---------------------------------------------------------

    def _load_ce(self) -> dict:
        if not self._ce_path.exists():
            raise FileNotFoundError(
                f"Configure Experiments config not found:\n  {self._ce_path}\n"
                "Run and save the LevyLab Configure Experiments VI first."
            )
        with open(self._ce_path, encoding="utf-8") as f:
            return json.load(f)

    def _connect_instruments(self, instruments: list[dict]) -> None:
        for inst in instruments:
            lv_class, name, address = inst["LVClass"], inst["Type"], inst["Address"]
            if self.verbose:
                print(f"  -> Connecting to {name} @ {address or 'no address'}...")
            ref = self._registry.get(lv_class)
            if ref is None:
                raise RuntimeError(
                    f"No driver for '{lv_class}' ({name}). Enable it with "
                    f"`flex list --drivers` / `flex enable <driver>`, or add it to "
                    "flex_drivers.levylab."
                )
            cls = load_ref(ref) if isinstance(ref, str) else ref
            driver = cls(name, address) if address else cls(name)
            inst["FlexClass"] = type(driver).__name__
            self.add_instrument(driver, name)
            if self.verbose:
                print(f"     OK ({inst['FlexClass']})")

    def _connect_transport_server(self) -> None:
        ref = self._registry.get("__transport_server__")
        if ref is None:
            return
        try:
            cls = load_ref(ref) if isinstance(ref, str) else ref
            self.add_instrument(cls("Transport"), "Transport")
        except Exception as e:
            self.log.warning("Transport server not connected: %s", e)

    def _slow_init_warning(self, seconds: float) -> None:
        self.log.warning(
            "CESession initialization is taking longer than %ss - check instrument "
            "connections, addresses, and that the LabVIEW apps are running.",
            seconds,
        )

    def __repr__(self) -> str:
        return (
            f"CESession(device='{self.ce.device}', user='{self.user}', "
            f"station='{self.ce.station}', instruments={len(self.instruments)})"
        )

    def _repr_html_(self) -> str:
        from html import escape

        from flex.display import card, table

        instrument_rows = [
            [
                escape(i["Type"]),
                escape(i["Address"] or "—"),
                f"<code>{escape(i['LVClass'] or '—')}</code>",
                f"<span class='ok'>{escape(i['FlexClass'])}</span>"
                if i["FlexClass"]
                else "<span class='bad'>not connected</span>",
            ]
            for i in self.ce.instruments
        ]
        wiring_rows = [
            [escape(str(ch)), escape(electrode), escape(label)]
            for ch, (electrode, label) in self.ce.wiring.items()
        ]
        sections = [
            ("Connected Instruments", table(["Type", "Address", "LV Class", "Flex Class"], instrument_rows))
        ]
        if wiring_rows:
            sections.append(("Wiring", table(["Ch", "Electrode", "Label"], wiring_rows)))
        return card(
            "CE Session",
            {
                "User": self.user,
                "Device": self.ce.device,
                "Station": self.ce.station,
                "Last Update": self.ce.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                if self.ce.timestamp
                else "—",
                "Description": self.ce.description or "—",
                "Device Path": self.ce.device_path or "—",
            },
            sections,
        )


def _levylab_registry() -> dict[str, str]:
    try:
        from flex_drivers.levylab import lvclass_registry
    except ImportError as e:
        raise ImportError(
            "CESession needs the LevyLab drivers. Install them with: "
            "flex install flex-drivers   (or: flex ecosystem use levylab)"
        ) from e
    registry = lvclass_registry()
    registry.setdefault("__transport_server__", "flex_drivers.levylab.transport_server:TransportServer")
    return registry
