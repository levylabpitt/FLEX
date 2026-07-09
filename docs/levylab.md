# LevyLab Guide

The LevyLab ecosystem connects FLEX to the lab's LabVIEW **Instrument
Framework** (IF): each instrument runs as an IF app exposing a JSON-RPC API
over ZMQ, experiments are configured in the **Configure Experiments VI**, data
goes to TDMS + Nextcloud, metadata to the lab PostgreSQL, and Asana is updated
through n8n.

## Setup (once per machine)

```
pip install flex
flex ecosystem use ecosystems/levylab.toml
set NEXTCLOUD_PASSWORD=...        # or add to the machine environment
```

## CESession

`CESession` is an `Experiment` bootstrapped from the Configure Experiments VI:
it reads `Control Experiment.json`, connects a driver to every configured IF
app (matched by LabVIEW class), and attaches them by their CE type.

```python
from flex import CESession, Scan, sweep
import numpy as np

with CESession() as exp:                       # user/device/wiring from the VI
    exp.DAQ.set_ao_dc(1, 0.0)
    print(exp.wiring)                          # {lockin ch: (electrode, label)}

    gate = exp.DAQ.parameters.get("ao1_dc") or (lambda v: exp.DAQ.set_ao_dc(1, v))
    Scan(sweep(gate, np.linspace(0, 1, 101), delay=0.1)) \
        .measure(results=exp.DAQ.get_results) \
        .on_abort(lambda: exp.DAQ.set_ao_dc(1, 0.0)) \
        .run(exp, name="gate sweep")
```

Everything from the base `Experiment` applies: measurements write TDMS files
(per the levylab config), records land in PostgreSQL, `exp.update()` picks up
instruments added in the VI while running, and n8n fires on start/end.

## Talking to IF apps directly

Every IF driver is a `ZMQInstrument`; drivers are thin, and raw access is
always available:

```python
from flex_drivers_levylab.lockin import Lockin

with Lockin("lockin", "tcp://localhost:29170") as li:
    li.set_ao_amplitude(1, 0.1)         # sends setAO_Amplitude
    print(li.get_results())
    print(li.help())                    # the IF app's own method list
    li.call("setSweep", {...})          # any method, verbatim
```

Errors from the IF (`error` in the JSON-RPC reply) raise
`ZMQInstrumentError`; a dead app raises `TimeoutError` and the connection
recovers on the next call.

## Non-IF instruments

Nothing requires the Instrument Framework: a plain VISA/serial instrument
(e.g. `flex_drivers.srs.SR7270`) registers into the same session next to IF
drivers:

```python
with CESession() as exp:
    exp.add(SR7270, "lockin2", serial="12345")
```

## Testing drivers without LabVIEW

`flex_protocols.testing.FakeIFServer` is an in-process fake IF app:

```python
from flex_protocols.testing import FakeIFServer

with FakeIFServer({"getResults": {"X": [1.0]}}) as server:
    li = Lockin("li", server.address)
    assert li.get_results() == {"X": [1.0]}
```

## The historical database

v2 writes to its own PostgreSQL tables (`experiments`, `measurements`,
`notes`). The v1 tables (`exp`, `meas`, `cell_log`) are untouched; migrating
them is a planned one-off — see the [migration notes](migration-v1-to-v2.md).
