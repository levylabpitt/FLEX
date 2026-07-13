# Instruments & drivers

A FLEX driver is an ordinary Python class. It inherits a connection from a
protocol base class, declares its knobs as *parameters*, and adds plain
methods for everything else. Nothing needs to be registered before you can
use it.

## The Instrument base class

`flex.instrument.Instrument` holds everything that does not depend on how the
instrument is connected: name, per-instrument logger (`inst.<name>`), the
parameter registry, `snapshot()`, `idn()`, and context-manager lifecycle
(`with ... :` closes the connection on exit). Protocol classes add the wire:
`query`/`write` for text protocols, `call` for JSON-RPC.

## Parameters

`add_parameter` registers a named, unit-carrying get/set handle:

```python
def add_parameter(self, name, *, get_cmd=None, set_cmd=None,
                  getter=None, setter=None, get_parser=None,
                  unit="", vals=None, doc="")
```

- `get_cmd` / `set_cmd` are command templates sent through the instrument's
  `query`/`write`; `set_cmd` is formatted with the value
  (`"SOUR:VOLT {}"`), `get_parser` converts the reply string (`float`).
- `getter` / `setter` are arbitrary callables, for instruments whose methods
  already exist. Give one style or the other, not both.
- `vals` is an optional validator, checked on every set.

A parameter is callable — no value reads, one value writes:

```python
k.voltage = k.add_parameter("voltage", get_cmd="SOUR:VOLT?",
                            set_cmd="SOUR:VOLT {}", get_parser=float, unit="V")
k.voltage(0.5)     # set
k.voltage()        # get -> 0.5
```

Sweeps and measurements consume parameters directly: the column name and unit
in the data file come from the parameter (see
[Experiments & data](experiments.md)).

Two validators exist: `Numbers(min, max)` accepts any real number in range —
including numpy scalars, excluding `bool` — and `Enum(*values)` accepts a
fixed set. Both raise on `set` before anything reaches the hardware.

## Protocol base classes

`flex-protocols` provides one base per connection type:

| Class | Connection | Talk to it with |
|---|---|---|
| `VISAInstrument` | GPIB / USB / RS-232 via VISA / TCPIP INSTR | `query(cmd)`, `write(cmd)` |
| `TCPInstrument` | raw TCP socket, line-based text | `query(cmd)`, `write(cmd)` |
| `SerialInstrument` | COM port | `query(cmd)`, `write(cmd)` |
| `ZMQInstrument` | JSON-RPC 2.0 over a ZMQ REQ socket | `call(method, params)` |

All four connect **eagerly in `__init__`** and raise if the connection cannot
be opened — constructing a driver instance means you are connected. All take
a `timeout` in seconds and accept `**kwargs` passed up to `Instrument`.

### ZMQInstrument specifics

`ZMQInstrument` speaks the LevyLab Instrument-Framework dialect of JSON-RPC
(but works with any JSON-RPC-over-ZMQ endpoint). On connect it sends an `ACK`
to verify the endpoint (disable with `connect_check=False`).

- `call(method, params)` returns the JSON-RPC `result`.
- A JSON-RPC `error` response raises `ZMQInstrumentError` (carries `.code`
  and `.data`).
- A missed reply raises `TimeoutError` **and resets the REQ socket** — a REQ
  socket that missed its reply is otherwise stuck forever, so the next call
  works again.
- `idn()` and `help()` wrap the IF built-ins `IDN` and `HELP`.

## Driver packages and the catalog

Drivers live in vendor folders inside `flex_drivers` (`srs/`, `colby/`,
`rotrics/`, `levylab/`). The package exports one plain dict:

```python
CATALOG: dict[str, str] = {
    "srs.sr7270": "flex_drivers.srs.sr7270:SR7270",
    "levylab.lockin": "flex_drivers.levylab.lockin:Lockin",
    ...
}
```

Importing `flex_drivers` imports no driver module (and no zmq/pyvisa); the
values are `"module:Class"` references resolved lazily.

Two ways to get a driver class:

- **Direct import — always works.** A driver is just a class:
  `from flex_drivers.srs.sr7270 import SR7270`. No installation state, no
  enablement, nothing gates imports.
- **By name**, through the catalog: station configs (`driver =
  "srs.sr7270"`), `flex instruments --probe`, and the dashboard resolve
  driver names via `CATALOG` — and require the name to be enabled first.

`flex enable <name>` adds the name to `[drivers] enabled` in the active
config (installing the parent package first if needed). Every name-based
resolution (`load_station()`, `--probe`, the dashboard) refuses a driver
that isn't enabled, even if its package is installed — a deliberate gate on
the config-driven path, not on imports: direct imports and `CESession` (which
only ever connects instruments the Configure Experiments file says are
physically wired up) are unaffected either way.

## LevyLab drivers and lv_class

Drivers for LevyLab Instrument-Framework apps additionally carry a `lv_class`
class attribute — the LabVIEW class name the IF app reports:

```python
class Lockin(ZMQInstrument):
    lv_class = "Instrument.Lockin.lvclass"
```

`flex_drivers.levylab.lvclass_registry()` walks the catalog and builds
`{LabVIEW class name: "module:Class"}` from these attributes (plus
`lv_class_aliases` — the five v1 PPMS variants all map to the one `PPMS`
driver). `CESession` uses that registry to auto-connect a driver to every
instrument in the Configure Experiments VI file — see the
[LevyLab guide](../levylab.md). A driver with `lv_class = None` (e.g.
`TransportServer`) is never auto-discovered.

## SimulatedInstrument

`flex.SimulatedInstrument` behaves like a text-protocol instrument without
hardware: `replies` maps commands to canned responses, every command sent is
recorded in `.sent`, and `add_sim_parameter(name, initial=..., unit=...)`
creates an in-memory readable/settable parameter. It powers the
[Quickstart](../quickstart.md) example, tests, and dry runs. For testing ZMQ
drivers against a fake IF app, see
[Write a driver](../tutorials/write-a-driver.md#7-test-without-hardware).
