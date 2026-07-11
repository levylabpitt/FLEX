# Quickstart

## Install

```powershell
irm flex.levylab.org/install.ps1 | iex
```

This brings in the five default packages (`flex-core`, `flex-protocols`,
`flex-db`, `flex-datatypes`, `flex-exp`). No configuration is needed — data
goes to HDF5 files and a SQLite database under your user data directory.
(Developing FLEX itself, or on another OS? Install editable from a clone —
see the README's Development section.)

## Your first experiment (no hardware needed)

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

What happened:

- an **experiment record** was created (id, user, start/end time, instruments),
- the scan swept `gate`, read `x` at every point, and wrote both columns —
  with units — to an **HDF5 file**,
- a **log file** captured everything, and Jupyter cells are recorded as notes,
- if you had pressed **Ctrl-C**, the file would have been finalized, the
  measurement marked *aborted*, and the `on_abort` cleanup would have run.

Browse it:

```
flex experiments
flex measurements <experiment-id>
```

## A real instrument

Any VISA instrument works the same way — drivers are one inheritance:

```python
from flex_protocols import VISAInstrument

class Keithley2400(VISAInstrument):
    def __init__(self, name="k2400", resource="GPIB0::24::INSTR"):
        super().__init__(name, resource)
        self.voltage = self.add_parameter(
            "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {}",
            get_parser=float, unit="V",
        )

with Experiment("jane") as exp:
    k = exp.add(Keithley2400, resource="GPIB0::24::INSTR")
    Scan(sweep(k.voltage, np.linspace(0, 1, 51), delay=0.1)) \
        .measure(current=lambda: k.query("MEAS:CURR?")) \
        .run(exp, name="IV")
```

`flex new driver MyInstrument --protocol visa` scaffolds this for you.

## Measurements without scans

For full control, drive the measurement yourself:

```python
with exp.measurement("noise vs time") as m:
    m.register(k.voltage)              # read on every point, with units
    for _ in range(1000):
        m.read_point(t=time.time())    # registered params + your columns
    m.add_array("spectrum", psd)       # free-form arrays
    m.add_note("AC line filter engaged")
```

## Next steps

- [Build an ecosystem](build-an-ecosystem.md) — configure your lab's database,
  storage, data format, and hooks in one file.
- [LevyLab guide](levylab.md) — `CESession` and the Instrument Framework.
- `flex dashboard` — manage packages and browse experiments in the browser.
