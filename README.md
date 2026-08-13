# FLEX — Framework for Laboratory EXperiments

![](/docs/flex-logo-v2.png)

FLEX is a modular Python platform for running laboratory experiments: instrument
control, autonomous sweeps, data files, experiment records, and lab-specific
integrations — with one-command setup for new users.

```powershell
irm flex.levylab.org/install.ps1 | iex
```

(Windows; see [`install.ps1`](install.ps1). Already have Python + a venv you
manage yourself? `pip install -e packages/flex-core[visa] -e packages/flex-exp
-e packages/flex-drivers -e packages/flex` from a clone works too — see
[Development](#development).)

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

FLEX is a handful of packages, split where installation actually differs;
the installer gives you the three default ones (via the `flex` metapackage).

| Package | What it is | Installed by default |
|---|---|---|
| `flex-core` | Instrument model, protocol bases (VISA/TCP/Serial/ZMQ), config, DB backends (SQLite/PostgreSQL), data writers (HDF5/TDMS), dashboard, CLI | ✅ |
| `flex-exp` | `Experiment`, `Measurement`, `Scan`, lab sessions (`CESession`) | ✅ |
| `flex-drivers` | Instrument drivers, by vendor (including LevyLab, over ZMQ) | ✅ |
| `flex-nextcloud` | Nextcloud file storage | opt-in |
| `flex-asana` | Asana comms backend: a task per experiment | opt-in |

Optional dependencies are extras on flex-core: `flex-core[visa]`,
`[zmq]`, `[serial]`, `[postgres]`, `[tdms]`, or `[all]`.

## Configuration

One `flex.toml` per PC describes the whole setup: the station's instruments
and the settings for every service (database, storage, data format, comms,
hooks). No config at all is a valid setup — SQLite + HDF5 + local files
under your user data directory. A lab shares an example config in
[`examples/`](examples/) that each machine copies and adjusts; see the
[configuration guide](docs/concepts/configuration.md).

## The CLI and the dashboard

```
flex drivers                 # every driver available in this environment
flex config show             # the active configuration
flex experiments             # browse recorded experiments
flex instruments --probe     # test-connect every configured instrument
flex new driver Keithley2400 # scaffold a driver
python -m flex dashboard     # all of the above, in the browser
```

## Writing a driver

Inherit from the protocol class matching how the instrument is connected:

```python
from flex.protocols import VISAInstrument

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

Plain pip works too: `pip install -e packages/flex-core[all] -e packages/flex-exp ...`

## License

MIT — see [LICENSE](LICENSE).
