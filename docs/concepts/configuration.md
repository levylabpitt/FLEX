# Configuration & stations

One TOML file — `flex.toml` — describes a PC's whole FLEX setup: the
services everyone shares (database, storage, data format, comms, hooks) and
the station wired to that bench. With no configuration at all, FLEX still
works: SQLite metadata, HDF5 data files, local storage under the user data
directory.

## The hierarchy

- The **config file** holds the service settings for this machine — database,
  storage, data format, hooks. A lab typically keeps a shared example in the
  repo ([examples/levylab.toml](https://github.com/levylabpitt/flex/blob/v3/examples/levylab.toml))
  that each PC copies and adjusts.
- A **station** is one bench's instrument set: a `[stations.<name>]` block
  mapping instrument names to drivers and addresses. Stations are inherently
  per-machine — your bench's addresses are not your neighbor's.
- An **instrument entry** names a driver and an address:

```toml
[stations.cryo1.instruments.lockin]
driver = "srs.sr7270"
address = "USB0::0x0A2D::0x001B::12345::RAW"
```

Extra keys in an instrument entry pass straight through to the driver's
constructor as keyword arguments.

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
component it names (including station drivers) resolves in this
environment.

## Stations at runtime

`exp.load_station("cryo1")` instantiates every instrument in the block —
resolving each `driver` name through the driver registry, passing the
address and extra keys — and registers them on the experiment. With
`[lab] station` set (or only one station defined), the name argument is
optional. `flex instruments --probe` test-connects the same entries from
the shell.

The LevyLab setup replaces station config with the Configure Experiments
VI: see [CESession](experiments.md#cesession).
