# FLEX — Framework for Laboratory EXperiments

![](/docs/flex-logo-v2.png)

FLEX is a modular Python platform for running laboratory experiments: instrument
control, autonomous sweeps, data files, experiment records, and lab-specific
integrations — with one-command setup for new users.

```powershell
irm flex.levylab.org/install.ps1 | iex
```

(Windows; see [`install.ps1`](install.ps1). Already have Python + a venv you
manage yourself? `pip install -e packages/flex-core -e packages/flex-protocols[visa]
-e packages/flex-db -e packages/flex-datatypes -e packages/flex-exp -e packages/flex`
from a clone works too — see [Development](#development).)

```python
from flex import Experiment, Scan, sweep, SimulatedInstrument
import numpy as np

with Experiment("jane") as exp:
    sim = exp.add(SimulatedInstrument, "demo")
    gate = sim.add_sim_parameter("gate", unit="V")
    x = sim.add_sim_parameter("x", initial=0.5, unit="V")

    Scan(sweep(gate, np.linspace(0, 1, 101), delay=0.01)) \
        .measure(sim.parameters["x"]) \
        .on_abort(lambda: gate(0)) \
        .run(exp, name="gate sweep")
```

That's a complete, autonomous, safely-abortable experiment: data lands in an
HDF5 file, metadata (who/when/what/where-is-the-file) in SQLite, and a per-
experiment log file — all under your user data directory, no configuration
needed. Swap `SimulatedInstrument` for a real one to run it on hardware.

## Packages

FLEX is a collection of small packages; the installer gives you the five
default ones. Everything else is opt-in via the package manager.

| Package | What it is | Installed by default |
|---|---|---|
| `flex-core` | Instrument model, data & metadata services, package manager, dashboard, CLI | ✅ |
| `flex-protocols` | `VISAInstrument`, `TCPInstrument`, `SerialInstrument`, `ZMQInstrument` base classes | ✅ |
| `flex-db` | Metadata database backends: SQLite (default), PostgreSQL | ✅ |
| `flex-exp` | `Experiment`, `Measurement`, `Scan`, lab sessions (`CESession`) | ✅ |
| `flex-datatypes` | HDF5 (default format) and TDMS (LabVIEW-compatible) data writers | ✅ |
| `flex-drivers` | Instrument drivers, by vendor (including LevyLab, over ZMQ) | opt-in |
| `flex-nextcloud` | Nextcloud file storage | opt-in |
| `flex-asana` | Asana notifications via n8n | opt-in |

## Ecosystems

An **ecosystem** is a lab's complete FLEX setup in one TOML manifest: which
packages to install and how everything is configured (database, storage, data
format, hooks, stations, enabled drivers). `default` (generic, no config
needed) ships with `flex-core`; lab-specific ones like `levylab` live in this
repo's own [`ecosystems/`](ecosystems/) folder — forks are free to delete or
replace them without touching `flex-core` at all. Activate one by name, or
point at your own manifest file.

```
flex ecosystem use levylab
```

installs the LevyLab stack (Instrument-Framework drivers, PostgreSQL, TDMS,
Nextcloud, Asana hooks) and activates its configuration. A new lab member is
productive in one command; a new lab writes one file.

## The CLI and the dashboard

```
flex list [--drivers]        # what's available / installed / enabled
flex install flex-datatypes  # add a package
flex enable levylab.lockin   # enable one driver (auto-installs its package)
flex ecosystem show          # the active configuration
flex experiments             # browse recorded experiments
flex instruments --probe     # test-connect every configured instrument
flex new driver Keithley2400 # scaffold a driver
flex dashboard               # all of the above, in the browser
```

## Writing a driver

Inherit from the protocol class matching how the instrument is connected:

```python
from flex_protocols import VISAInstrument

class Keithley2400(VISAInstrument):
    def __init__(self, name="k2400", resource="GPIB0::24::INSTR"):
        super().__init__(name, resource)
        self.voltage = self.add_parameter(
            "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {}",
            get_parser=float, unit="V",
        )
```

See [docs/](docs/) for the full guides, and
[docs/migration-v1-to-v2.md](docs/migration-v1-to-v2.md) if you are coming
from FLEX v1 (which remains on the `main` branch).

## Development

The repo is a [uv](https://docs.astral.sh/uv/) workspace:

```
uv sync          # everything, editable, one lockfile
uv run pytest packages -q
uv run ruff check packages
```

Plain pip works too: `pip install -e packages/flex-core -e packages/flex-protocols ...`

## License

MIT — see [LICENSE](LICENSE).
