# FLEX

**Framework for Laboratory EXperiments** — a modular Python platform for
running laboratory experiments: instrument control, autonomous sweeps, data
files, experiment records, and lab-specific integrations, with one-command
setup for new users.

```powershell
irm flex.levylab.org/install.ps1 | iex
```

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
HDF5 file, metadata in SQLite, and a per-experiment log file — all under your
user data directory, no configuration needed. Swap `SimulatedInstrument` for
a real one to run it on hardware.

## Where to go

- **[Quickstart](quickstart.md)** — install and run your first experiment in
  five minutes.
- **[Concepts](concepts/architecture.md)** — how the pieces fit together:
  packages, instruments, experiments, ecosystems, the dashboard.
- **[Tutorials](tutorials/write-a-driver.md)** — write a driver, build your
  lab's ecosystem, set up a LevyLab station.
- **[Reference](reference/drivers/index.md)** — every driver and integration,
  generated from the code.
- **[Migrating from v1](migration-v1-to-v2.md)** — v1 stays on the `main`
  branch; this maps every v1 concept to its v2 home.

## The short version

| You want to… | FLEX gives you |
|---|---|
| talk to an instrument | `VISAInstrument` / `ZMQInstrument` / `TCPInstrument` / `SerialInstrument` base classes, and a [catalog of ready drivers](reference/drivers/index.md) |
| run a sweep safely | `Scan` + `sweep`: Ctrl-C finalizes the file, marks the measurement aborted, runs your cleanup |
| keep records | every experiment and measurement is recorded (SQLite by default, PostgreSQL for labs) |
| share a lab setup | an [ecosystem](concepts/ecosystems.md): one TOML manifest, one `flex ecosystem use` command |
| manage it all visually | `python -m flex dashboard` — packages, drivers, ecosystems, and experiment browsing in the browser |
