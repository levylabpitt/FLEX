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

import importlib
import json
import os
import pkgutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import threading
from flex.inst.levylab.TransportServer import Transport


_CONFIG_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / \
    "Levylab" / "Control Experiment" / "Control Experiment.json"

_SUMMARY_TEMPLATE = """
<style>
    .ce-session {{
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 13px;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 10px;
        padding: 20px 24px;
        max-width: 760px;
    }}
    .ce-session .header {{
        font-size: 11px;
        letter-spacing: 3px;
        color: #4ade80;
        text-transform: uppercase;
        margin-bottom: 12px;
    }}
    .ce-session .header::before {{ content: '● '; }}
    .ce-session .meta-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px 24px;
        margin-bottom: 16px;
    }}
    .ce-session .meta-item {{ display: flex; flex-direction: column; }}
    .ce-session .meta-label {{
        font-size: 9px;
        letter-spacing: 2px;
        color: #475569;
        text-transform: uppercase;
    }}
    .ce-session .meta-value {{
        font-size: 13px;
        color: #f1f5f9;
        font-weight: 600;
    }}
    .ce-session .section {{
        font-size: 9px;
        letter-spacing: 2px;
        color: #475569;
        text-transform: uppercase;
        margin: 14px 0 6px;
    }}
    .ce-session table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
    }}
    .ce-session th {{
        text-align: left;
        padding: 6px 10px;
        font-size: 9px;
        letter-spacing: 2px;
        color: #475569;
        border-bottom: 1px solid #1e293b;
        text-transform: uppercase;
    }}
    .ce-session td {{
        text-align: left;
        padding: 7px 10px;
        color: #94a3b8;
        border-bottom: 1px solid #0f172a;
    }}
    .ce-session td:first-child {{ color: #e2e8f0; font-weight: 600; }}
    .ce-session .found {{ color: #4ade80; }}
    .ce-session .not-found {{ color: #f87171; font-style: italic; }}
    .ce-session code {{
        font-size: 11px;
        color: #64748b;
        background: #1e293b;
        padding: 2px 6px;
        border-radius: 3px;
    }}
</style>
<div class="ce-session">
    <div class="header">CE Session Initialized</div>
    <div class="meta-grid">
        <div class="meta-item"><span class="meta-label">User</span><span class="meta-value">{user}</span></div>
        <div class="meta-item"><span class="meta-label">Device</span><span class="meta-value">{device}</span></div>
        <div class="meta-item"><span class="meta-label">Station</span><span class="meta-value">{station}</span></div>
        <div class="meta-item"><span class="meta-label">Last Update</span><span class="meta-value">{timestamp}</span></div>
        <div class="meta-item" style="grid-column: span 2"><span class="meta-label">Description</span><span class="meta-value">{description}</span></div>
        <div class="meta-item" style="grid-column: span 2"><span class="meta-label">Device Path</span><span class="meta-value" style="font-size:11px; color:#64748b">{device_path}</span></div>
    </div>
    <div class="section">Connected Instruments</div>
    <table>
        <thead><tr><th>Type</th><th>Address</th><th>LV Class</th><th>Flex Class</th></tr></thead>
        <tbody>{inst_rows}</tbody>
    </table>
    <div class="section">Wiring</div>
    <table>
        <thead><tr><th>Ch</th><th>Electrode</th><th>Label</th></tr></thead>
        <tbody>{wiring_rows}</tbody>
    </table>
</div>
"""


@dataclass
class ExperimentSession:
    user: str
    device: str
    device_path: str
    description: str
    station: str
    instruments: list[dict]   # {Type, Address, ClassPath, LVClass, FlexClass}
    wiring: dict              # {lockin_ch: (electrode, label)}
    timestamp: Optional[datetime] = None


def _is_interactive() -> bool:
    try:
        from IPython import get_ipython
        return get_ipython() is not None
    except ImportError:
        return False


def _find_and_instantiate(lv_class_filename: str, address: str) -> tuple: # Added address param
    """
    Scan flex.inst.levylab for a module whose _LABVIEW_CLASS_NAME matches
    lv_class_filename. Returns (instance, class_name) or (None, None).
    """
    package = importlib.import_module("flex.inst.levylab")
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        try:
            module = importlib.import_module(f"flex.inst.levylab.{module_name}")
            if getattr(module, "_LABVIEW_CLASS_NAME", None) == lv_class_filename:
                cls = getattr(module, module_name)
                # Now passing the address from JSON to the constructor
                return cls(address=address), cls.__name__ 
        except Exception:
            continue
    return None, None


class CESession:
    """
    Initializes a Flex experiment session driven by the LevyLab Configure
    Experiment VI. Connected instruments are auto-discovered from
    flex.inst.levylab via _LABVIEW_CLASS_NAME and attached as attributes
    by Type, e.g.:

        myexp.DAQ        # Lockin instance
        myexp.Amplifier  # Krohn_Hite_7008 instance

    A rich HTML summary is displayed automatically in VSCode interactive /
    Jupyter environments. No output is produced in plain script runs.

    Parameters
    ----------
    config_path : str or Path, optional
        Override default config location.
    """

    def __init__(self, config_path: Optional[str | Path] = None, timeout: float = 10.0, verbose: bool = False):
            self._config_path = Path(config_path) if config_path else _CONFIG_PATH
            self._instrument_attrs: set[str] = set()
            self.verbose = verbose

            def log(msg):
                if self.verbose: print(f"[*] {msg}")

            # Start watchdog
            timer = threading.Timer(timeout, self._timeout_warning, [timeout])
            timer.start()

            try:
                log(f"Loading config from: {self._config_path}")
                config_data = self._load_config()
                
                log("Parsing experiment metadata and wiring...")
                self.session = self._parse(config_data)
                
                # --- Initialize Transport Server ---
                log("Initializing Transport Server...")
                self.Transport = Transport()  # Assigned specifically to .Transport
                self._instrument_attrs.add("Transport")
                
                log(f"Found {len(self.session.instruments)} instruments. Initializing drivers...")
                self._instantiate_instruments()
                
                log("Initialization complete.")
            finally:
                timer.cancel()

            if _is_interactive():
                self._display_summary()

    def _timeout_warning(self, seconds):
        """Prints a warning if initialization exceeds the timeout."""
        print(f"\n[!] WARNING: CESession initialization is taking longer than {seconds}s.")
        print("    Please check instrument connections, addresses, and LabVIEW status.\n")

    # ------------------------------------------------------------------
    # Loading & parsing
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Configure Experiment config not found at:\n  {self._config_path}\n"
                "Ensure the LevyLab Configure Experiment VI has been run and saved."
            )
        with open(self._config_path, encoding="utf-8") as f:
            return json.load(f)

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
                "LVClass":   Path(cp_full).name if cp_full else "—",
                "FlexClass": None,   # populated during instantiation
            })

        # Wiring: {lockin_ch: (electrode, label)}, skip empty electrodes
        wc = raw.get("Wiring Configuration", {})
        wiring = {
            ch: (el, lb)
            for ch, el, lb in zip(
                wc.get("Lockin Ch", []),
                wc.get("KH", {}).get("Electrodes", []),
                wc.get("KH", {}).get("Labels", []),
            )
            if el
        }

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

    # ------------------------------------------------------------------
    # Instrument instantiation
    # ------------------------------------------------------------------

    def _instantiate_instruments(self, instruments: list[dict] | None = None):
            targets = instruments if instruments is not None else self.session.instruments
            for inst in targets:
                attr_name = inst["Type"]
                addr = inst["Address"]
                
                if self.verbose:
                    print(f"    -> Connecting to {attr_name} @ {addr or 'No Address'}...", end=" ", flush=True)
                
                obj, class_name = _find_and_instantiate(inst["LVClass"], addr)
                inst["FlexClass"] = class_name
                
                if obj is None:
                    if self.verbose: print("FAILED")
                    raise RuntimeError(f"No driver found for '{inst['LVClass']}'")
                
                setattr(self, attr_name, obj)
                self._instrument_attrs.add(attr_name)
                
                if self.verbose: print(f"OK ({class_name})")

    # ------------------------------------------------------------------
    # HTML summary (interactive only)
    # ------------------------------------------------------------------

    def _display_summary(self):
        from IPython.display import display, HTML
        s = self.session

        # --- Added Transport to the instrument rows ---
        # We manually create the row for Transport since it's not in self.session.instruments
        transport_row = (
            f"<tr>"
            f"<td>Transport</td>"
            f"<td>{getattr(self.Transport, '_address', 'Local')}</td>"
            f"<td><code>flex.inst.levylab</code></td>"
            f"<td class='found'>Transport</td>"
            f"</tr>"
        )

        inst_rows = transport_row + "".join(
            f"<tr>"
            f"<td>{i['Type']}</td>"
            f"<td>{i['Address'] or '—'}</td>"
            f"<td><code>{i['ClassPath']}</code></td>"
            f"<td class=\"{'found' if i['FlexClass'] else 'not-found'}\">"
            f"{i['FlexClass'] if i['FlexClass'] else 'Not found'}</td>"
            f"</tr>"
            for i in s.instruments
        )
        wiring_rows = "".join(
            f"<tr><td>{ch}</td><td>{el}</td><td>{lb}</td></tr>"
            for ch, (el, lb) in s.wiring.items()
        )

        display(HTML(_SUMMARY_TEMPLATE.format(
            user=s.user,
            device=s.device,
            station=s.station,
            timestamp=s.timestamp.strftime("%Y-%m-%d %H:%M:%S") if s.timestamp else "—",
            description=s.description or "—",
            device_path=s.device_path or "—",
            inst_rows=inst_rows,
            wiring_rows=wiring_rows,
        )))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_device_path(self) -> Path:
        """Return the device path as a Path object, for use in file saving."""
        return Path(self.session.device_path)

    def get_instrument(self, instrument_type: str) -> Optional[dict]:
        """Return the instrument dict matching the given Type."""
        for inst in self.session.instruments:
            if inst["Type"].lower() == instrument_type.lower():
                return inst
        return None

    def get_wiring(self) -> dict:
        """Return wiring as {lockin_channel: (electrode, label)}."""
        return self.session.wiring

    def update(self):
        """Reload config and instantiate any newly added instruments."""
        # Preserve FlexClass for already-instantiated instruments
        prev_flex = {i["Type"]: i["FlexClass"] for i in self.session.instruments}

        self.session = self._parse(self._load_config())

        for inst in self.session.instruments:
            if inst["Type"] in self._instrument_attrs:
                inst["FlexClass"] = prev_flex.get(inst["Type"])
        new_types = {i["Type"] for i in self.session.instruments} - self._instrument_attrs
        if new_types:
            self._instantiate_instruments([
                i for i in self.session.instruments if i["Type"] in new_types
            ])
            for t in new_types:
                print(f"New instrument added: {t}")
        if _is_interactive():
            self._display_summary()
        else:
            print("Session refreshed.")

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
        s = self.session
        return (
            f"CESession(device='{s.device}', user='{s.user}', "
            f"station='{s.station}', instruments={len(s.instruments)})"
        )
    
    # --- Context Manager Protocol ---
    def __enter__(self):
        """Allows usage: with CESession() as exp:"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatically closes instruments when the block exits."""
        if self.verbose:
            print("\n[*] Block exited. Cleaning up instruments...")
        self.close_all()