# flex

The standard FLEX installation. Installing this metapackage gives you:

- **flex-core** — instrument model, experiment data & metadata services, package manager, ecosystem configuration, CLI
- **flex-protocols** — `VISAInstrument`, `TCPInstrument`, `SerialInstrument`, `ZMQInstrument` base classes (VISA support included by default)
- **flex-db** — metadata database backends (SQLite by default)
- **flex-exp** — the `Experiment` handler, `Measurement`, and `Scan` tools

```
pip install flex
```

Optional packages (`flex install <name>` or pip): `flex-drivers`, `flex-drivers-levylab`,
`flex-nextcloud`, `flex-asana`, `flex-tdms`, `flex-dashboard`.
