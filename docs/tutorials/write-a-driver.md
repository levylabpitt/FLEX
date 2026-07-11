# Write a driver

A FLEX driver is one class: a protocol base supplies the connection, you
declare parameters and methods. This tutorial writes a driver for a
fictitious `Acme4000` source-meter and ends with the optional steps —
registration, LevyLab integration, hardware-free tests.

Background on the pieces: [Instruments & drivers](../concepts/instruments.md).

## 1. Pick the protocol base

Match how the instrument is physically connected:

| Connection | Base | Constructor takes |
|---|---|---|
| GPIB, USB-TMC, VISA of any kind | `VISAInstrument` | `resource` string |
| Raw TCP socket, line-based text | `TCPInstrument` | `host`, `port` |
| COM port | `SerialInstrument` | `port` (plus `baudrate=`) |
| JSON-RPC over ZMQ (LevyLab IF apps) | `ZMQInstrument` | `address` |

All connect eagerly in `__init__` — constructing the driver either connects
or raises.

## 2. Scaffold the file

```
flex new driver Acme4000 --protocol visa
```

This writes `acme4000.py` **in the current directory** (change with
`--out <dir>`; it refuses to overwrite an existing file). Protocols:
`visa` (default) | `tcp` | `serial` | `zmq`. The generated file:

```python
"""FLEX driver for Acme4000."""

from flex_protocols import VISAInstrument


class Acme4000(VISAInstrument):
    def __init__(self, name: str = "acme4000", resource: str = "GPIB0::1::INSTR", **kwargs):
        super().__init__(name, resource, **kwargs)

        # Declare parameters: name, commands (or getter/setter), unit.
        ...
```

## 3. Fill in parameters and methods

```python
from flex.instrument import Numbers
from flex_protocols import VISAInstrument


class Acme4000(VISAInstrument):
    def __init__(self, name: str = "acme4000", resource: str = "GPIB0::1::INSTR", **kwargs):
        super().__init__(name, resource, **kwargs)

        self.voltage = self.add_parameter(
            "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {}",
            get_parser=float, unit="V", vals=Numbers(-20, 20),
        )
        self.current = self.add_parameter(
            "current", get_cmd="MEAS:CURR?", get_parser=float, unit="A",
        )

    def output(self, on: bool) -> None:
        self.write(f"OUTP {'ON' if on else 'OFF'}")
```

Guidelines:

- Anything you will sweep or measure should be a parameter — sweeps and data
  files pick up its name and unit automatically.
- One-shot actions (reset, output on/off, autorange) are plain methods.
- Use `vals=` to reject dangerous setpoints before they reach the hardware.
- The base class already gives you `idn()`, `snapshot()`, `close()`, logging,
  and context-manager support; override `idn()` only for non-SCPI
  instruments.

## 4. Use it — no registration needed

A driver is just a class. Import it and go:

```python
from acme4000 import Acme4000
from flex import Experiment, Scan, sweep
import numpy as np

with Experiment("jane") as exp:
    src = exp.add(Acme4000, resource="GPIB0::24::INSTR")
    Scan(sweep(src.voltage, np.linspace(0, 1, 51), delay=0.1)) \
        .measure(src.current) \
        .on_abort(lambda: src.voltage(0)) \
        .run(exp, name="IV")
```

For many drivers this is the end of the tutorial.

## 5. Optional: register it for name-based resolution

Registration only matters if you want the driver addressable *by name* — in
`[stations.*]` config blocks, `flex enable`, `flex instruments --probe`, and
the dashboard.

**Your own package.** Scaffold one and move the driver file in:

```
flex new package flex-drivers-mylab
```

This creates an installable package (`pyproject.toml`, `src/flex_drivers_mylab/`,
`tests/`) whose `__init__.py` holds the registry dict:

```python
CATALOG: dict[str, str] = {
    "mylab.acme4000": "flex_drivers_mylab.acme4000:Acme4000",
}
```

Install it (`pip install -e flex-drivers-mylab`), then point FLEX at the
registry with a `catalog.local.json` **next to your active ecosystem config**:

```json
{"flex-drivers-mylab": {"registries": {"drivers": "flex_drivers_mylab:CATALOG"}}}
```

The local catalog is merged over the built-in one at load time, so your
drivers now appear in `flex list --drivers` and resolve by name everywhere.

**Or contribute to `flex-drivers`.** Add a vendor folder
(`src/flex_drivers/acme/`), put the module there, and add one line to the
package's `CATALOG` in `src/flex_drivers/__init__.py`. The existing vendor
folders (`srs/`, `colby/`, `rotrics/`) are the pattern to copy.

## 6. LevyLab Instrument-Framework drivers

An IF app driver inherits `ZMQInstrument` and sets `lv_class` to the app's
LabVIEW class name so `CESession` can auto-connect it:

```python
from flex_drivers.levylab._commands import IFTemperatureCommands
from flex_protocols import ZMQInstrument


class MyCryostat(ZMQInstrument, IFTemperatureCommands):
    lv_class = "Instrument.MyCryostat.lvclass"

    def get_pressure(self) -> float:
        return self.call("getPressure")
```

- Wire methods are `self.call("<IF method name>", params)`; keep the exact
  IF spellings on the wire, snake_case on the Python side.
- If the app implements the standard IF temperature or magnet commands, mix
  in `IFTemperatureCommands` / `IFMagnetCommands` from
  `flex_drivers.levylab._commands` instead of rewriting them.
- Add the driver to the levylab `CATALOG`; `lvclass_registry()` picks up
  `lv_class` (and `lv_class_aliases`) automatically — there is no separate
  mapping to maintain.

## 7. Test without hardware

For ZMQ drivers, `flex_protocols.testing.FakeIFServer` is an in-process fake
IF app: give it canned results per method, then assert on both the returned
values and the exact wire traffic it recorded. This is how every LevyLab
driver in the repo is tested (`packages/flex-drivers/tests/test_levylab_drivers.py`):

```python
from flex_protocols.testing import FakeIFServer


def test_pressure():
    with FakeIFServer({"getPressure": 1.3e-6}) as server:
        with MyCryostat("cryo", server.address) as dev:
            assert dev.get_pressure() == 1.3e-6
        assert server.requests[-1]["method"] == "getPressure"
```

Handlers may be callables (`params -> result`) and may raise to produce a
JSON-RPC error; set `server.delay` to test timeout recovery.

For VISA/TCP/serial drivers there is no bundled simulator — the repo's
pattern (see `packages/flex-drivers/tests/test_sr7270.py`) is a small fake
resource class plus a monkeypatched `ResourceManager`, asserting on the
commands the driver writes. `SimulatedInstrument` covers the cases where you
only need canned query/reply behavior on top of the base `Instrument`.

## Checklist

- [ ] Correct protocol base; connection parameters have sensible defaults
- [ ] Sweepable/measurable quantities are parameters, with units
- [ ] Validators on anything that could damage a sample
- [ ] Driver works by direct import
- [ ] (optional) `CATALOG` entry + `catalog.local.json`, or a `flex-drivers` PR
- [ ] (LevyLab) `lv_class` set; command mixins used where they apply
- [ ] Tests pass without hardware
