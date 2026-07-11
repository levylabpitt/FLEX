# Architecture

FLEX is a monorepo of small packages. One package, `flex-core`, holds the
base classes and services; everything else plugs into it through a static
JSON catalog. There is no plugin framework, no entry-points, no registration
side effects — a "plugin" is a plain dict a package exports.

## The packages

| Package | What it is | Default |
|---|---|---|
| `flex-core` | Instrument model, data & metadata services, package manager, dashboard, CLI | yes |
| `flex-protocols` | `VISAInstrument`, `TCPInstrument`, `SerialInstrument`, `ZMQInstrument` base classes | yes |
| `flex-db` | Metadata database backends: SQLite (default), PostgreSQL | yes |
| `flex-exp` | `Experiment`, `Measurement`, `Scan`, lab sessions (`CESession`) | yes |
| `flex-datatypes` | HDF5 (default) and TDMS (LabVIEW-compatible) data writers | yes |
| `flex-drivers` | Instrument drivers, by vendor (including LevyLab, over ZMQ) | opt-in |
| `flex-nextcloud` | Nextcloud file storage | opt-in |
| `flex-asana` | Asana notifications via n8n | opt-in |

The installer gives you the five default packages. Opt-in packages arrive via
`flex install`, `flex enable <driver>`, or activating an
[ecosystem](ecosystems.md) that lists them.

## What lives in flex-core

Everything other packages build on:

- **Instrument model** — the `Instrument` base class and `Parameter`
  (see [Instruments & drivers](instruments.md)).
- **Data interfaces** — `DataWriter` (file formats) and `StorageBackend`
  (where finished files live), plus the built-in `LocalStorage`.
- **Metadata interface** — the `MetadataStore` ABC and the record dataclasses
  (`ExperimentRecord`, `MeasurementRecord`, `NoteRecord`).
- **EventBus** — small synchronous pub/sub for lifecycle hooks
  (see [Experiments & data](experiments.md#hooks-and-events)).
- **Ecosystem configuration** — the `FlexConfig` model and its
  resolution rules (see [Ecosystems & stations](ecosystems.md)).
- **Package manager, dashboard, CLI** — thin UIs over the above.

`flex-core` has no hardware, database, or file-format dependencies. Those
live in the packages that implement them.

## How packages plug in

The catalog (`packages/flex-core/src/flex/pkgmanager/catalog.json`) describes
every official package: group, summary, whether it is a default, which
component names it *provides*, and — the key part — a `registries` entry per
component group pointing at a dict the package exports:

```json
"flex-datatypes": {
  "provides": { "writer": ["hdf5", "tdms"] },
  "registries": { "writer": "flex_datatypes:WRITERS" }
}
```

`flex_datatypes.WRITERS` is a plain module-level dict:

```python
WRITERS: dict[str, str] = {
    "hdf5": "flex_datatypes.hdf5:HDF5Writer",
    "tdms": "flex_datatypes.tdms:TDMSWriter",
}
```

Same pattern everywhere: `flex_drivers:CATALOG` for drivers,
`flex_db:DB_BACKENDS` for metadata stores, `flex.data:STORAGE` and
`flex_nextcloud:STORAGE` for storage backends.

A lab extends the catalog without editing anything installed: a
`catalog.local.json` next to the active ecosystem config is merged on top of
the built-in one (per-package, by name). That is how a private driver package
becomes visible to `flex list`, `flex install`, and the dashboard — see
[Build an ecosystem](../build-an-ecosystem.md#extending-flex-itself).

## Name resolution

Configuration refers to components by short name; `flex.components` turns the
name into a class in three steps:

```
[data] writer = "hdf5"                     # config: a short name
        │
        ▼
catalog "registries" → flex_datatypes:WRITERS   # which dicts to consult
        │
        ▼
WRITERS["hdf5"] → "flex_datatypes.hdf5:HDF5Writer"   # a "module:Class" ref
        │
        ▼
import flex_datatypes.hdf5; HDF5Writer     # the class, instantiated with the
                                           # section's remaining options
```

Registries whose providing package is not installed are skipped. If a name
resolves to nothing, the error names the official package that provides it
("Install it with: flex install flex-datatypes"). Driver names
(`"levylab.lockin"`) resolve exactly the same way through the `drivers`
group.

## Installation

None of these packages are on PyPI. `flex install` (used by
`flex ecosystem use` and the dashboard) delegates to the environment's
installer — `uv pip` in a uv-managed venv, otherwise `python -m pip` — and
picks the source per package:

- inside a clone of this repo (a uv workspace), packages install **editable**
  from `packages/<name>`;
- everywhere else, from GitHub:
  `git+https://github.com/levylabpitt/flex.git@v2#subdirectory=packages/<name>`
  (branch overridable with `$FLEX_SOURCE_REF`).

Extras pass through: `flex-db[postgres]` installs the base package with its
PostgreSQL dependencies.
