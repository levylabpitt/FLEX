# flex

The standard FLEX installation. Installing this metapackage gives you:

- **flex-core** — instrument model, protocol base classes (`VISAInstrument`,
  `TCPInstrument`, `SerialInstrument`, `ZMQInstrument`; VISA support included
  by default), configuration, metadata database backends (SQLite by default),
  data writers (HDF5 by default), station server, runner, dashboard, CLI
- **flex-exp** — `Experiment`, `Measurement`, `Scan`, lab sessions
- **flex-drivers** — instrument drivers, by vendor (including LevyLab)

Opt-in packages: `flex-nextcloud`, `flex-asana`, installed editable from a
checkout (`pip install -e packages/flex-nextcloud`). Optional dependencies
are extras on flex-core: `[visa]`, `[serial]`, `[postgres]`, `[tdms]`,
`[app]`, `[all]`. The dashboard is served by the tray app (`flex app`, needs
`[app]`).
