# Migrating from FLEX v1 to v2

FLEX v2 is a clean break: v1 stays on the `main` branch and keeps working;
migrate scripts when convenient. This page maps every v1 concept to its v2
home.

## Setup

| v1 | v2 |
|---|---|
| clone repo + `pip install -e .` (one big package) | `irm flex.levylab.org/install.ps1 \| iex`, then `flex ecosystem use levylab` for the lab stack |
| hardcoded DB / Nextcloud / n8n endpoints in code | one manifest in the repo's `ecosystems/` folder: `flex ecosystem show` after activating `levylab` |
| secrets in source | environment variables (`NEXTCLOUD_PASSWORD`, `ASANA_ACCESS_TOKEN`) |

## Imports and classes

| v1 | v2 |
|---|---|
| `from flex.inst.base import Instrument` (ZMQ baked in) | `from flex_protocols import ZMQInstrument` (also `VISAInstrument`, `TCPInstrument`, `SerialInstrument`) |
| `from flex.inst.levylab.Lockin import Lockin` | `from flex_drivers.levylab.lockin import Lockin` |
| `inst._send_command(cmd, params)['result']` | `inst.call(cmd, params)` — errors now **raise** instead of returning `None` |
| `_LABVIEW_CLASS_NAME` module constant | `lv_class` class attribute; `flex_drivers.levylab.lvclass_registry()` derives the CESession lookup from it |
| `flex.inst.levylab.insttypes.*` empty mixins | `flex_drivers.levylab.capabilities` protocols (real methods; `exp.get(Temperature)`) |
| `from flex.exp.experiment import Experiment` | `from flex import Experiment` |
| `from flex.exp.CESession import CESession` | `from flex import CESession` |
| `flex.db.FLEXDB` (raw SQL, hardcoded host) | metadata store from config: SQLite default, `[db] backend = "postgres"` for the lab DB |
| `flex.tdms.flexTDMS.write_tdms` | `[data] writer = "tdms"` — every measurement writes TDMS automatically |
| `flex.nextcloud` | `[storage] backend = "nextcloud"` — files upload on measurement finish |
| `flex.exp.dbexptoAsana.trigger_n8n_dbexptoAsana()` (n8n) / `flex.asana.Asana` (hardcoded-token stub) | `[comms] backend = "asana"` — `flex-asana` talks to the Asana API directly, token from `ASANA_ACCESS_TOKEN` |
| `flex.exp.users` hardcoded `Literal` list | any user string; lab-side validation can hook `experiment.start` |
| `flex.exp.script_to_db.CellLogger` | built into `Experiment` (`cell_log=True`), stored in `flex_cells` |

## Method names

Driver methods are now snake_case; the wire protocol is unchanged:
`setAO_Amplitude(...)` → `set_ao_amplitude(...)` (still sends `setAO_Amplitude`).

## Behavior changes worth knowing

- **JSON-RPC errors raise `ZMQInstrumentError`** (v1 silently returned `None`).
- **A ZMQ timeout no longer wedges the connection** — the socket is reset and
  the next call works; you get a `TimeoutError` you can catch.
- **Ctrl-C during a `Scan` is safe**: the data file is finalized, the
  measurement is marked `aborted`, and `on_abort` cleanups run.
- **Experiment/measurement IDs** gained a random suffix
  (`20260709153053-bee7`) so two starts in the same second cannot collide.
- **Metadata store failures never kill a measurement** — they are logged and
  the experiment continues (opt into strictness with `[exp] strict_metadata = true`).
- The five `PPMS*` classes are one `PPMS` (they only differed in address);
  pass the address, or define stations in the config.

## Not carried over (deliberately)

- **The v1 `flex.asana.Asana` file contains a live, hardcoded Asana token —
  revoke it** (its v2 replacement reads `ASANA_ACCESS_TOKEN` from the
  environment instead; see the row above).
- `flex.lv` LabVIEW call helpers, `exp/pund.py` (experiment logic, not
  framework — rewrite as a `Scan` script), `exp/experiment_bak`.
- Newport/Ophir/Sphere drivers that require .NET or COM — tracked in
  [`packages/flex-drivers/DEFERRED.md`](https://github.com/levylabpitt/flex/blob/v2/packages/flex-drivers/DEFERRED.md).

## Postgres note

`PostgresStore` creates the v2 core schema as `flex_`-prefixed tables
(`flex_experiments`, `flex_measurements`, `flex_notes`, `flex_cells`,
`flex_logs`, `flex_instruments`) and does not touch the v1 `exp` / `meas` /
`cell_log` tables. Migrating that historical data (or pointing v2 at the same
tables) is a coordinated one-off step — plan it with the lab before switching
production.
