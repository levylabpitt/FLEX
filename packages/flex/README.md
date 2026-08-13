# flex

The standard FLEX installation. Installing this metapackage gives you:

- **flex-core** — instrument model, protocol base classes (`VISAInstrument`,
  `TCPInstrument`, `SerialInstrument`, `ZMQInstrument`; VISA support included
  by default), configuration, metadata database backends (SQLite by default),
  data writers (HDF5 by default), dashboard, CLI
- **flex-exp** — `Experiment`, `Measurement`, `Scan`, lab sessions
- **flex-drivers** — instrument drivers, by vendor (including LevyLab)

Optional packages (pip): `flex-nextcloud`, `flex-asana`. Optional
dependencies are extras on flex-core: `[zmq]`, `[serial]`, `[postgres]`,
`[tdms]`, `[all]`. The dashboard is part of flex-core: `python -m flex
dashboard`.
