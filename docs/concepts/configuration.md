# Configuration & instruments

One TOML file — `flex.toml` — describes a PC's whole FLEX setup: the
services everyone shares (database, storage, data format, comms, hooks) and
the instruments wired to that machine. With no configuration at all, FLEX
still works: SQLite metadata, HDF5 data files, local storage under the user
data directory.

## The pieces

- The **config file** holds the service settings for this machine — database,
  storage, data format, hooks. A lab typically keeps a shared example in the
  repo ([examples/levylab.toml](https://github.com/levylabpitt/flex/blob/v3/examples/levylab.toml))
  that each PC copies and adjusts.
- An **instrument entry** names a driver and an address. The entries are
  inherently per-machine — your bench's addresses are not your neighbor's:

```toml
[instruments.lockin]
driver = "srs.sr7270"
address = "USB0::0x0A2D::0x001B::12345::RAW"
```

Extra keys in an instrument entry pass straight through to the driver's
constructor as keyword arguments. Two special keys don't:

- `simulate = true` swaps the entry for a `SimulatedInstrument` stand-in,
  so a whole config (or any one instrument of it) can dry-run scripts with
  zero hardware; `driver` may even be omitted.
- `driver` accepts either a catalog name (`"srs.sr7270"`) or a direct
  `"module:Class"` reference — private driver packages need no
  registration.

A physical *station* (say a PPMS with one DAQ PC and one interface PC) can
span several machines; each machine's flex.toml lists just the instruments
it is wired to, and `[lab] station` labels which station the machine belongs
to — that label is stamped on every experiment record.

## Configuration resolution

At runtime the active configuration is found by a fixed precedence:

1. an explicit path argument (`Experiment(config=...)`, `flex config validate <path>`)
2. `$FLEX_CONFIG`
3. `./flex.toml` (the current directory)
4. `%LOCALAPPDATA%/flex/config.toml` (the per-user location)
5. built-in defaults (no file at all)

`./flex.toml` outranking the user config is the escape hatch: a project
folder can carry its own complete configuration without touching the
machine-wide one.

Every section is optional; short component names ("postgres", "tdms",
"nextcloud") resolve to classes through fixed registries — see
[Architecture](architecture.md#name-resolution). A component provided by an
optional package just needs that package installed:

```
uv pip install flex-core[postgres,tdms] flex-nextcloud flex-asana
```

`flex config show` prints the resolved configuration and its source;
`flex config validate <path>` checks a file's schema and that every
component it names (including instrument drivers) resolves in this
environment.

## Instruments at runtime

`exp.load_instruments()` instantiates every `[instruments.*]` entry —
resolving each `driver`, passing the address and extra keys — and registers
them on the experiment; pass names (`exp.load_instruments("lockin")`) to
load a subset. `flex instruments --probe` test-connects the same entries
from the shell.

The same entries have two more consumers: `Station.load()` builds them as a
standalone station (no experiment), and `flex serve` hosts that station
over ZMQ — port set by `[server] port` (default 29500). See
[Architecture](architecture.md#the-station-server).

## Background logging

`flex serve` can log parameters to the database around the clock:

```toml
[instruments.spectrometer]
driver = "acme.spec2000:Spec2000"
address = "tcp://localhost:29200"
log = ["spectrum", "temperature"]   # parameters to log
log_interval = 60                   # seconds between reads
```

The reads go through the instrument's normal command queue, so they never
collide with a running experiment; every update lands in the `flex_monitor`
table (and any *set* of a logged parameter is recorded too). Browse history
with `flex monitor`, or stream live with `flex monitor --follow`. Anything
loggable must be a parameter — wrap a driver method with
`add_parameter(..., getter=...)` if needed.

**If the database is unreachable** (Postgres down, network blip), nothing is
lost: with a non-SQLite backend, points buffer in a local SQLite file
(`<data_root>/monitor_outbox.db`) and replay automatically once the database
comes back — even across a `flex serve` restart, since the outbox is a file,
not memory. Instrument control is unaffected either way; only logging pauses.

The LevyLab setup replaces instrument config with the Configure Experiments
VI: see [CESession](experiments.md#cesession).
