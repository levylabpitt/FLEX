# Add instruments: IF, VISA and serial

[Write a driver](write-a-driver.md) shows the mechanics of one driver. This
page shows how a driver fits into the rest of FLEX, and why, using the three
cases you will meet in the lab:

- a new instrument with its own **LabVIEW app** (Instrument Framework, "IF")
- a motorized stage on **VISA**
- an amplifier on a **serial** port

## The rule behind the design

A driver is the only code that knows an instrument's language. Everything
else (the station server, the client proxy, the runner, the dashboard, data
files) is generic: it asks the driver what it offers and works with that.

```
 script / notebook / dashboard            generic: knows no instrument
        │  "call stage.move_to(5)"
        ▼
 station server  (flex serve)             generic: leases, queues, events
        │
        ▼
 YOUR DRIVER                               the only instrument-specific code
   parameters + methods                    "move_to(5)" -> "MOVE 5.0"
        │
        ▼
 protocol base class                       flex-core: the connection
   VISAInstrument · SerialInstrument · ZMQInstrument
        │
        ▼
 the instrument  (GPIB / COM port / LabVIEW app)
```

Two consequences, and they decide most of what follows:

- **Write the driver once, against the instrument.** Scripts on any PC, the
  dashboard and the runner reach it through the server. Nothing is
  duplicated per client, and a fix lands in one place.
- **A driver describes itself by being Python.** Its parameters and public
  methods are what the dashboard shows and what remote scripts can call.
  There is no separate interface file to keep in sync.

## Pick the base from how you reach the instrument

| The instrument is reached by | Base class | You talk to it with |
|---|---|---|
| a LabVIEW app (ZMQ, JSON-RPC) | `ZMQInstrument` | `self.call("verb", params)` |
| VISA: GPIB, USB-TMC, TCPIP | `VISAInstrument` | `self.query(cmd)`, `self.write(cmd)` |
| a COM port | `SerialInstrument` | `self.query(cmd)`, `self.write(cmd)` |

The base opens the connection in `__init__` and raises if it cannot. A
driver that fails to connect never takes the station down: the server skips
it and shows it as "failed to load" with the reason.

## 1. An IF app: the Hall probe

A LabVIEW app already exists and answers JSON-RPC verbs. The driver is a
thin, faithful wrapper: it keeps the app's verb and key spellings on the
wire and gives them Python names.

```python
from flex.protocols import ZMQInstrument


class HallProbe(ZMQInstrument):
    lv_class = "Instrument.HallProbe.lvclass"

    def __init__(self, name="hall", address="tcp://localhost:29300", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("field", getter=self.get_field, unit="T")

    def get_field(self) -> float:
        reply = self.call("getField")
        return reply["field"] if isinstance(reply, dict) else reply

    def set_range(self, tesla: float) -> None:
        self.call("setRange", {"Range": tesla})
```

Why it looks like this:

- **Exact verbs on the wire, snake_case in Python.** `set_range` sends
  `setRange` with the key `Range`, copied from the app. The LabVIEW side is
  the reference, so a mismatch is a bug in the driver, not in the app.
- **Unwrap replies in the driver.** Apps answer in different shapes (a bare
  number, a dict, `null` for setters). Callers should get a number. If you
  also want the full reply, keep a second method for it
  (`get_field_status`), as the PPMS driver does for temperature.
- **`field` is a parameter, `set_range` a method.** Anything you will sweep,
  log or plot is a parameter, because it carries a name and a unit into data
  files and the dashboard. One-off actions are methods.
- **`lv_class`** is the app's LabVIEW class name. It lets `CESession`
  recognise the app on a lab PC. Skip it if the app has no class name.

To find an app's verbs, connect and call `help()`: it lists what the app
implements. Run a read-only probe first (see `examples/experiments/probe.py`)
and look at the real replies before writing the unwrapping.

## 2. VISA: the motorized stage

The stage speaks text commands. The base gives `query` and `write`; the
driver turns them into parameters and actions.

```python
import time

from flex.instrument import Numbers
from flex.protocols import VISAInstrument


class Stage(VISAInstrument):
    def __init__(self, name="stage", resource="GPIB0::7::INSTR", **kwargs):
        super().__init__(name, resource, read_termination="\r\n", **kwargs)
        self.add_parameter(
            "position", get_cmd="POS?", set_cmd="MOVE {}",
            get_parser=float, unit="mm", vals=Numbers(0, 50),
        )

    def is_moving(self) -> bool:
        return self.query("MOT?") == "1"

    def wait_until_stopped(self, timeout: float = 60.0, poll: float = 0.1) -> None:
        began = time.monotonic()
        while self.is_moving():
            if time.monotonic() - began > timeout:
                raise TimeoutError(f"Stage still moving after {timeout:.0f} s")
            time.sleep(poll)

    def stop(self) -> None:
        self.write("STOP")
```

Why:

- **`get_cmd` / `set_cmd` for plain commands.** One line each, no wrapper
  functions. `get_parser` turns the reply text into a number.
- **`vals=Numbers(0, 50)` rejects a bad setpoint before it reaches the
  hardware.** Put a validator on anything that can crash a stage, burn a
  sample or overheat a magnet.
- **Waiting has a timeout.** A move that never finishes should fail loudly,
  not hang a run.
- **Keep driver calls short.** The server runs one command at a time per
  instrument. A method that blocks for minutes also blocks every other
  command to that stage, including the `stop()` an abort needs. For long
  motions, start the move and poll from the script instead.

## 3. Serial: the amplifier

```python
from flex.instrument import Enum
from flex.protocols import SerialInstrument


class Amplifier(SerialInstrument):
    def __init__(self, name="amp", port="COM4", baudrate=19200, **kwargs):
        super().__init__(name, port, baudrate=baudrate, terminator=b"\r", **kwargs)
        self.add_parameter(
            "gain", get_cmd="GAIN?", set_cmd="GAIN {}",
            get_parser=int, vals=Enum(1, 10, 100, 1000),
        )
        self.add_parameter("coupling", get_cmd="CPL?", set_cmd="CPL {}", vals=Enum("AC", "DC"))

    def idn(self) -> dict[str, str | None]:
        return {"vendor": "Acme", "model": self.query("ID?"), "serial": None, "firmware": None}
```

Why:

- **The serial settings belong to the instrument, so they live in the
  driver.** Line terminator and encoding are fixed by the amplifier. The
  baud rate may differ per unit, so it is an argument that `flex.toml` can
  override.
- **`Enum` lists the legal values.** The amplifier only has four gains, so
  anything else is rejected before it is sent.
- **Override `idn()` for non-SCPI instruments.** The default sends `*IDN?`,
  which most serial devices do not understand.

## Wire them into the station

Put the three classes in a package (`flex new package flex-drivers-mylab`
scaffolds one) or any importable module, then list them in the PC's
`flex.toml`:

```toml
[instruments.hall]
driver  = "flex_drivers_mylab.hall:HallProbe"
address = "tcp://localhost:29300"

[instruments.stage]
driver  = "flex_drivers_mylab.stage:Stage"
address = "GPIB0::7::INSTR"

[instruments.amp]
driver   = "flex_drivers_mylab.amp:Amplifier"
address  = "COM4"
baudrate = 9600
```

- `driver` is a `module:Class` reference, so nothing needs registering. To
  give it a short name like `levylab.lockin`, add one line to a `CATALOG`
  dict (see [Write a driver](write-a-driver.md#5-optional-register-it-for-name-based-resolution)).
- `address` is the first argument after the name: a ZMQ address, a VISA
  resource string, or a COM port. Any other key (`baudrate`) is passed to the
  driver as a keyword.

Start the station (the tray app, or `flex serve`) and the three drivers
become one station:

```
 script · notebook · dashboard             clients, on any PC
          │  FLEX station protocol (call / get / set / describe)
          ▼
 ┌─ flex serve ─────────────────────────────────────────────┐
 │  one worker thread per instrument                         │
 │                                                           │
 │  hall: HallProbe     stage: Stage        amp: Amplifier   │
 │   ZMQInstrument       VISAInstrument      SerialInstrument│
 └───────┬──────────────────────┬────────────────────┬──────┘
         │ ZMQ                  │ VISA               │ COM4
         ▼                      ▼                    ▼
   LabVIEW Hall app        motorized stage        amplifier
```

From here you get, with no extra code:

```python
station.hall.field()               # parameter read
station.stage.position(12.5)       # parameter set, validated
station.stage.wait_until_stopped() # any public method
station.amp.gain(100)
```

The dashboard's Station tab shows all three with live readouts and input
boxes, derived from the parameters. A run script holds the station's lease
while it runs, so nobody else's writes interleave with it.

## What keeps a driver compatible with all this

- **Public methods are the remote API.** Names starting with `_` stay
  private and cannot be called remotely.
- **Return plain values.** Numbers, strings, lists and dicts cross the wire
  as JSON. Convert numpy arrays with `.tolist()`.
- **Connect in `__init__`, release in `close()`.** The server calls
  `close()` on shutdown; make it safe to call twice.
- **Raise, don't print.** An exception becomes an error reply the caller
  sees. A printed message is lost in a background process.

## Test without the hardware

Each base has an easy stand-in; see [Write a driver](write-a-driver.md#7-test-without-hardware):

- **IF drivers:** `FakeIFServer` answers JSON-RPC verbs and records what the
  driver sent, so you can assert on the exact verb and key spelling.
- **VISA and serial:** a small fake resource that records the commands
  written and returns canned replies (see `tests/test_sr7270.py`).
