"""
flex.exp.CESession
------------------
Initializes a Flex experiment session from the LevyLab Configure Experiment VI
config file located at:
    %LOCALAPPDATA%\\Levylab\\Control Experiment\\Control Experiment.json

Usage:
    from flex.exp import CESession
    myexp = CESession()
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / \
    "Levylab" / "Control Experiment" / "Control Experiment.json"

_REGISTRY_PATH = Path(__file__).parent.parent / "inst" / "levylab_instrument_registry.json"

@dataclass
class ExperimentSession:
    user: str
    device: str
    device_path: str
    description: str
    station: str
    instruments: list[dict]       # {Type, Address, ClassPath, ClassPathFull}
    wiring: dict                  # {lockin_ch: (electrode, label)}
    timestamp: Optional[datetime] = None

class CESession:
    """
    Initializes a Flex experiment session driven by the LevyLab Configure
    Experiment VI. Connected instruments are auto-instantiated from the
    registry and attached as attributes by Type, e.g.:
        myexp.DAQ        # MCLockin instance
        myexp.Amplifier  # KrohnHite7008 instance

    Parameters
    ----------
    config_path : str or Path, optional
        Override default config location.
    registry_path : str or Path, optional
        Override default registry location.
    verbose : bool, optional
        Print summary on init (default True).
    """

    def __init__(
        self,
        config_path: Optional[str | Path] = None,
        registry_path: Optional[str | Path] = None,
        verbose: bool = True,
    ):
        self._config_path   = Path(config_path)   if config_path   else _CONFIG_PATH
        self._registry_path = Path(registry_path) if registry_path else _REGISTRY_PATH
        self._registry = self._load_registry()
        self._instrument_attrs: set[str] = set()

        self.session = self._parse(self._load_config())
        self._instantiate_instruments()

        if verbose:
            self._print_summary()

    def _load_config(self) -> dict:
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Configure Experiment config not found at:\n  {self._config_path}\n"
                "Ensure the LevyLab Configure Experiment VI has been run and saved."
            )
        with open(self._config_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_registry(self) -> dict:
        if not self._registry_path.exists():
            raise FileNotFoundError(
                f"Instrument registry not found at:\n  {self._registry_path}"
            )
        with open(self._registry_path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}

    def _parse(self, raw: dict) -> ExperimentSession:
        exp  = raw.get("Experiment", {})
        meta = {}
        if "json" in raw:
            try:
                meta = json.loads(raw["json"])
            except (json.JSONDecodeError, TypeError):
                pass
        device_meta = meta.get("Device", {})

        # Connected instruments only — skip generic stubs
        instruments = []
        for inst in exp.get("Instruments", []):
            cp_full = inst.get("class path", "")
            if "levylab/instrument framework/instrument types" in cp_full.replace("\\", "/").lower():
                continue
            instruments.append({
                "Type":      inst.get("Type", "Unknown"),
                "Address":   inst.get("Address", ""),
                "ClassPath": Path(cp_full).stem if cp_full else "—",
            })

        # Wiring: {lockin_ch: (electrode, label)}, skip empty electrodes
        wc = raw.get("Wiring Configuration", {})
        channels   = wc.get("Lockin Ch", [])
        electrodes = wc.get("KH", {}).get("Electrodes", [])
        labels     = wc.get("KH", {}).get("Labels", [])
        wiring = {
            ch: (el, lb)
            for ch, el, lb in zip(channels, electrodes, labels)
            if el
        }

        # Timestamp
        try:
            ts = datetime.fromisoformat(device_meta.get("Time", "")[:19])
        except (ValueError, TypeError):
            ts = None

        return ExperimentSession(
            user=exp.get("User", device_meta.get("User", "Unknown")),
            device=exp.get("Device", device_meta.get("Device", "Unknown")),
            device_path=exp.get("Device Path", ""),
            description=exp.get("Device Description", ""),
            station=exp.get("Instrument", "Unknown"),
            instruments=instruments,
            wiring=wiring,
            timestamp=ts,
        )

    def _instantiate_instruments(self, instruments: list[dict] | None = None):
        targets = instruments if instruments is not None else self.session.instruments
        for inst in targets:
            attr_name = inst["Type"]
            stem      = inst["ClassPath"]

            if stem not in self._registry:
                raise KeyError(
                    f"No registry entry for '{stem}' (Type: {attr_name}).\n"
                    f"Add to {self._registry_path}:\n"
                    f'  "{stem}": {{"module": "flex.inst.<pkg>.<module>", "class": "<Class>"}}'
                )

            entry = self._registry[stem]
            if "module" not in entry or "class" not in entry:
                raise ValueError(f"Malformed registry entry for '{stem}': {entry}")

            module_path = entry["module"]
            class_name  = entry["class"]
            namespace   = {}
            try:
                exec(f"from {module_path} import {class_name}", namespace)
            except Exception as e:
                raise ModuleNotFoundError(
                    f"Failed: from {module_path} import {class_name}\n{e}"
                ) from e

            setattr(self, attr_name, namespace[class_name]())
            self._instrument_attrs.add(attr_name)

    def _print_summary(self):
        s   = self.session
        sep = "─" * 68
        print(f"\n┌{sep}┐")
        print(f"│  CE SESSION INITIALIZED".ljust(69) + "│")
        print(f"├{sep}┤")
        print(f"│  User        : {s.user:<52}│")
        print(f"│  Device      : {s.device:<52}│")
        print(f"│  Station     : {s.station:<52}│")
        print(f"│  Description : {(s.description or '—'):<52}│")
        print(f"│  Last Update : {s.timestamp.strftime('%Y-%m-%d %H:%M:%S') if s.timestamp else '—':<52}│")
        print(f"├{sep}┤")
        print(f"│  {'Type':<18} {'Address':<18} {'Class Path':<28}│")
        print(f"│  {'─'*18} {'─'*18} {'─'*28}│")
        for inst in s.instruments:
            print(f"│  {inst['Type'][:17]:<18} {(inst['Address'] or '—')[:17]:<18} {inst['ClassPath'][:27]:<28}│")
        print(f"├{sep}┤")
        print(f"│  {'Ch':<8} {'Electrode':<18} {'Label':<38}│")
        print(f"│  {'─'*8} {'─'*18} {'─'*38}│")
        for ch, (el, lb) in s.wiring.items():
            print(f"│  {str(ch):<8} {el:<18} {lb:<38}│")
        print(f"└{sep}┘\n")


    def get_instrument(self, instrument_type: str) -> Optional[dict]:
        """Return the first instrument dict matching the given Type."""
        for inst in self.session.instruments:
            if inst["Type"].lower() == instrument_type.lower():
                return inst
        return None

    def get_instruments(self, instrument_type: str) -> list[dict]:
        """Return all instrument dicts matching the given Type."""
        return [i for i in self.session.instruments if i["Type"].lower() == instrument_type.lower()]

    def get_wiring(self) -> dict:
        """Return wiring as {lockin_channel: (electrode, label)}."""
        return self.session.wiring

    def update(self, verbose: bool = True):
        """Reload config and instantiate any newly added instruments."""
        self.session = self._parse(self._load_config())
        new_types = {i["Type"] for i in self.session.instruments} - self._instrument_attrs
        if new_types:
            self._instantiate_instruments([
                i for i in self.session.instruments if i["Type"] in new_types
            ])
            if verbose:
                for t in new_types:
                    print(f"New instrument added: {t}")
        if verbose:
            print("Session refreshed.")
            self._print_summary()

    def close_all(self):
        """Call close() on every instantiated instrument that supports it."""
        closed, skipped = [], []
        for attr_name in self._instrument_attrs:
            inst = getattr(self, attr_name, None)
            if inst is not None and hasattr(inst, "close"):
                try:
                    inst.close()
                    closed.append(attr_name)
                except Exception as e:
                    print(f"{attr_name}.close() raised: {e}")
            else:
                skipped.append(attr_name)
        if closed:  print(f"Closed: {', '.join(closed)}")
        if skipped: print(f"No close(): {', '.join(skipped)}")

    def __repr__(self):
        """Object representation with Exp Summary"""
        s = self.session
        return (
            f"CESession(device='{s.device}', user='{s.user}', "
            f"station='{s.station}', instruments={len(s.instruments)})"
        )