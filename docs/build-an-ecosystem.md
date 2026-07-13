# Build an Ecosystem

An **ecosystem** is your lab's FLEX setup in one TOML manifest: the packages
to install plus every setting. Share the file; new members run one command.

```
flex ecosystem use mylab.toml
```

## The manifest

```toml
[ecosystem]
name = "mylab"
packages = ["flex-datatypes", "flex-drivers"]   # installed on activation

[lab]
name = "mylab"
station = "cryo1"

[db]
backend = "sqlite"            # or "postgres" with dsn = "postgresql://..."

[storage]
backend = "local"             # or "nextcloud" with url/user (+ NEXTCLOUD_PASSWORD env)

[data]
writer = "hdf5"               # or "tdms"
root = "D:/data"

[comms]
backend = "none"              # or "asana" (flex-asana) -- see its package docstring for config

[hooks]                       # dotted refs, subscribed to experiment events
on_experiment_end = ["some_package.hooks:notify"]

[drivers]
enabled = ["srs.sr7270"]

[stations.cryo1.instruments.lockin]
driver = "srs.sr7270"
address = "USB0::0x0A2D::0x001B::12345::RAW"
```

Every section is optional — omit it and the default applies. Backends may
define their own extra keys (like `dsn` above); they pass straight through.

## How the configuration is found

1. explicit path (`Experiment(config=...)` / `load_config(path)`)
2. the `FLEX_CONFIG` environment variable
3. `./flex.toml` in the working directory
4. the activated config (`%LOCALAPPDATA%/flex/config.toml`)
5. nothing → pure defaults (SQLite + HDF5 + local files)

`flex ecosystem show` prints the resolved result; `flex ecosystem validate
mylab.toml` checks a manifest and whether its components are installed.

## Stations

`[stations.*]` describes which instruments live where. Then:

```python
with Experiment("jane") as exp:
    exp.load_station("cryo1")      # constructs and registers every instrument
    exp.lockin.x()                 # ready to use
```

`flex instruments --probe` test-connects everything from the shell.

## Extending FLEX itself

Labs add their own components as normal Python packages:

- a **driver package**: `flex new package flex-drivers-mylab` scaffolds one —
  fill drivers in, list them in its `CATALOG`, and they appear in
  `flex list --drivers`;
- a **DB backend / data writer / storage backend / comms backend**: subclass
  `MetadataStore`, `DataWriter`, `StorageBackend`, or `CommsBackend` from
  `flex-core` and export a `{name: "module:Class"}` registry dict from your
  package — the name you register is what goes in the manifest;
- **hooks**: any function `fn(event, experiment, **payload)`, referenced from
  `[hooks]`.

To make a component discoverable by `flex install`/`flex list` without
editing an installed package, add it to a `catalog.local.json` next to your
active ecosystem config, e.g.
`{"flex-drivers-mylab": {"registries": {"drivers": "flex_drivers_mylab:CATALOG"}}}`.

The FLEX repo hosts official packages in `packages/`; PRs welcome — the
LevyLab drivers (`flex_drivers.levylab`) alongside `flex-datatypes`,
`flex-nextcloud`, `flex-asana` are the reference implementation.

To make your own lab's manifest activatable by bare name (`flex ecosystem use
mylab`) rather than a full path, drop it in this repo's own `ecosystems/`
folder (not inside any package — see `flex.pkgmanager.ecosystems`). Only
`default.toml` ships inside `flex-core` itself; everything else here is this
repo's own content, so a fork can add, remove, or replace manifests without
touching core at all.
