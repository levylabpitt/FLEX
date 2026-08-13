# Architecture

A lab PC running FLEX is an **instrument server**: it connects to the
physical instruments, logs to a database, writes data files, and (soon)
accepts remote control from scripts on other PCs. FLEX is organized in three
layers, deliberately mirroring the
[bluesky/ophyd](https://blueskyproject.io/) ecosystem's division of labor —
device abstraction, experiment orchestration, and an always-on service layer
— while staying small enough to read in an afternoon:

```
┌───────────────────────────────────────────────────────────────┐
│  flex-exp        Experiment · Measurement · Scan · CESession  │  orchestration
├───────────────────────────────────────────────────────────────┤
│  flex-core       Station services: config (flex.toml),        │  services
│                  metadata DB, data writers, storage, events,  │
│                  dashboard, CLI                               │
├───────────────────────────────────────────────────────────────┤
│  flex-core       Instrument · Parameter                       │  devices
│  + flex-drivers  VISA / ZMQ / TCP / Serial bases, drivers     │
└───────────────────────────────────────────────────────────────┘
```

The rough bluesky correspondence: `Instrument`/`Parameter` play the role of
ophyd's `Device`/`Signal` (a uniform interface over heterogeneous hardware),
`flex-exp` plays the role of the RunEngine and plans (orchestrating
measurements, streaming records to subscribers), and the FLEX station
services play the role EPICS IOCs serve at a beamline — the per-machine
process that owns the hardware and its bookkeeping.

## The packages

| Package | What it is | Default |
|---|---|---|
| `flex-core` | Instrument model, protocol bases, config, DB backends, data writers, storage, events, dashboard, CLI | yes |
| `flex-exp` | `Experiment`, `Measurement`, `Scan`, lab sessions (`CESession`) | yes |
| `flex-drivers` | Instrument drivers, by vendor (including LevyLab, over ZMQ) | yes |
| `flex-nextcloud` | Nextcloud file storage | opt-in |
| `flex-asana` | Asana comms backend: a task per experiment | opt-in |

(The `flex` package is a metapackage that installs the three defaults.)

Package boundaries follow *installation* boundaries — a package exists only
if someone would install it separately. Everything always installed together
(protocols, DB backends, file writers) lives inside `flex-core` as plain
modules: `flex.protocols`, `flex.db`, `flex.datatypes`. Optional
dependencies are extras on flex-core:

```
pip install flex-core[visa]          # pyvisa
pip install flex-core[zmq]           # pyzmq
pip install flex-core[serial]        # pyserial
pip install flex-core[postgres]      # psycopg
pip install flex-core[tdms]          # npTDMS
```

## What lives in flex-core

- **Instrument model** — the `Instrument` base class and `Parameter`
  (see [Instruments & drivers](instruments.md)), plus the protocol bases
  (`VISAInstrument`, `ZMQInstrument`, `TCPInstrument`, `SerialInstrument`).
- **Configuration** — the `FlexConfig` model, loaded from one `flex.toml`
  per PC (see [Configuration & instruments](configuration.md)).
- **Data interfaces** — `DataWriter` (HDF5 default, TDMS for LabVIEW) and
  `StorageBackend` (local default, Nextcloud opt-in).
- **Metadata interface** — the `MetadataStore` ABC and its record dataclasses,
  with SQLite (default) and PostgreSQL backends (see
  [Metadata records](experiments.md#metadata-records)).
- **EventBus** — small synchronous pub/sub for lifecycle hooks
  (see [Experiments & data](experiments.md#hooks-and-events)).
- **Dashboard & CLI** — thin UIs over the above.

## Name resolution

Configuration refers to components by short name; `flex.components` turns
the name into a class through a fixed registry table:

```
[data] writer = "hdf5"                          # config: a short name
        │
        ▼
flex.components._REGISTRIES["writer"]           # → flex.datatypes:WRITERS
        │
        ▼
WRITERS["hdf5"] → "flex.datatypes.hdf5:HDF5Writer"   # a "module:Class" ref
        │
        ▼
import flex.datatypes.hdf5; HDF5Writer          # instantiated with the
                                                # section's remaining options
```

Each registry is a plain module-level dict. Registries provided by optional
packages (`flex_drivers:CATALOG`, `flex_nextcloud:STORAGE`,
`flex_asana:COMMS`) are skipped when the package isn't installed, and a
missing component's error message names the package that provides it. There
is no plugin framework, no entry points, no registration side effects.

## The station server

A `Station` is the `[instruments.*]` set of flex.toml as a live object. It
runs in-process (`Station.load()` in a notebook) or as a long-running
server:

```
flex.toml ──► Station ──┬── notebook mode:   station.lockin.gate(0.5)
                        └── server mode:     `flex serve`
                                               ├─ ZMQ ROUTER: JSON-RPC commands
                                               └─ ZMQ PUB:    event stream

other PC:  station = flex.connect("tcp://bench-pc:29500")
           station.lockin.gate(0.5)   # RemoteInstrument proxy — identical API
           station.subscribe(print)   # live parameter events
```

Two ideas carry the design:

1. **One event stream.** Every parameter read/set is an event
   `(seq, parameter, value, unit, ts)` on the station bus, published over
   ZMQ PUB; the DB logger, live dashboard, and remote monitors are all just
   subscribers. The stream is monitoring, not the data record — data files
   and the metadata store stay authoritative, so dropped events are
   harmless.
2. **Local and remote instruments share one API.** `RemoteInstrument`
   mirrors `Instrument` (parameters and public methods are built from the
   server's `describe`), so `flex-exp` code runs unchanged either way. The
   wire protocol is the same JSON-RPC dialect the LevyLab LabVIEW
   Instrument-Framework speaks — one protocol for the whole lab, and any
   IF-compatible client can talk to a FLEX server.

Commands for different instruments run concurrently (a worker per
instrument); commands for the same instrument are serialized, since
hardware isn't reentrant. Background DB logging and the live dashboard view
are the next subscribers to be built on the stream.

## Installation

None of these packages are on PyPI. The installer (`install.ps1`) and the
docs use plain pip/uv against the GitHub repo:

- inside a clone of this repo (a uv workspace), packages install **editable**
  from `packages/<name>`;
- everywhere else, from GitHub:
  `git+https://github.com/levylabpitt/flex.git@v3#subdirectory=packages/<name>`.

Extras pass through: `flex-core[postgres]` installs the base package with
its PostgreSQL dependencies.
