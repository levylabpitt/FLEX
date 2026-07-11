"""FLEX demo: the "default" ecosystem — zero configuration, everything local.

Run it from the repo root:

    uv run python tests/test_default_ecosystem.py

What this exercises:

  1. A "normal" driver (SimulatedInstrument) under the default ecosystem --
     a complete, working experiment with real data written to disk.
  2. A LevyLab driver, imported and used *directly* -- proving a driver class
     doesn't need to be "enabled" or part of the active ecosystem's package
     list to be usable. `flex enable` / an ecosystem's `packages` list only
     matter for *name-based* resolution (`driver = "levylab.lockin"` in a
     [stations.*] block); importing the class yourself always works once the
     package is installed.
  3. Both together in one Experiment.

Where things land (default ecosystem: SQLite metadata, HDF5 data, local
storage -- the printouts below show the exact resolved paths on this
machine):

  - Metadata (who/when/what/where-is-the-file):
        <data_root>/flex.db                                   (SQLite)
  - Measurement data files:
        <data_root>/<year>/<experiment_id>/<measurement_id>.h5
  - Per-experiment log file:
        <data_root>/<experiment_id[:4]>/<experiment_id>/experiment.log

  <data_root> defaults to flex.ecosystem.default_data_root(), i.e.
  %LOCALAPPDATA%/flex/data on Windows (see flex.ecosystem.APP_DIR).

Part 1 needs no network or real hardware. Part 2 (and the LevyLab half of
part 3) will legitimately time out -- there's no real LevyLab
Instrument-Framework app listening on tcp://localhost:29170 on this machine.
That's expected; the script explains it inline. On real hardware, with the
IF app actually running, the exact same code connects immediately.

Nothing here touches your real active ecosystem (%LOCALAPPDATA%/flex/config.toml)
-- the config used is FlexConfig()'s bare defaults, not whatever you last
activated with `flex ecosystem use` (see the note in the script for why).
"""

from __future__ import annotations

import numpy as np

from flex.ecosystem import FlexConfig, default_data_root
from flex.instrument import SimulatedInstrument
from flex_exp import Experiment, Scan, sweep


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# -----------------------------------------------------------------------------
section("The 'default' ecosystem")
# -----------------------------------------------------------------------------
# default.toml's content (db=sqlite, storage=local, writer=hdf5,
# handler=default) is *identical* to FlexConfig()'s bare Pydantic defaults --
# that's the whole point of the default ecosystem. So there's nothing to
# load: FlexConfig() alone gives the exact same result, and unlike
# load_config() (which reads whatever's actually active on this machine --
# could be levylab, could be anything), it's deterministic regardless of
# what you last ran `flex ecosystem use` with. A script deliberately testing
# "the default ecosystem" shouldn't depend on machine state to do it.
config = FlexConfig()
print(
    f"db.backend={config.db.backend}  storage.backend={config.storage.backend}  "
    f"data.writer={config.data.writer}  exp.handler={config.exp.handler}"
)
print(f"Data root on this machine: {default_data_root()}")


# -----------------------------------------------------------------------------
section("1. Normal driver (SimulatedInstrument) — fully local, no hardware")
# -----------------------------------------------------------------------------
with Experiment("demo-user", name="normal-driver-demo", config=config, cell_log=False) as exp:
    sim = exp.add(SimulatedInstrument, "bench")
    gate = sim.add_sim_parameter("gate", unit="V")
    x = sim.add_sim_parameter("x", initial=0.5, unit="V")

    Scan(sweep(gate, np.linspace(0, 1, 11), delay=0.0)) \
        .measure(sim.parameters["x"]) \
        .on_abort(lambda: gate(0)) \
        .run(exp, name="gate sweep")

    print(f"Experiment id: {exp.id}")
    print(f"Log file:      {exp.config.data.root / exp.id[:4] / exp.id / 'experiment.log'}")

print(f"-> metadata + data written under {default_data_root()}")
print("   browse it with:  flex experiments   /   flex measurements <id>   /   flex dashboard")


# -----------------------------------------------------------------------------
section("2. LevyLab driver, imported directly — no ecosystem needed to use it")
# -----------------------------------------------------------------------------
# flex-drivers isn't even in the "default" ecosystem's package list, and we
# never ran `flex enable levylab.lockin` -- doesn't matter. The class is just
# a class.
from flex_drivers.levylab.lockin import Lockin  # noqa: E402

try:
    # ZMQInstrument.__init__ connects eagerly and sends an ACK handshake, so
    # a missing/unreachable endpoint fails fast (here, after `timeout`
    # seconds) rather than lazily on first use. timeout is shortened from
    # the 5s default purely so this demo doesn't sit there for no reason.
    lockin = Lockin("lockin", "tcp://localhost:29170", timeout=2.0)
except Exception as e:
    print(f"Expected failure (no real LevyLab IF app running here): {e}")
else:
    lockin.close()
    print("Connected — did you actually have a Lockin IF app running on this machine?")


# -----------------------------------------------------------------------------
section("3. Both together in one Experiment")
# -----------------------------------------------------------------------------
with Experiment("demo-user", name="mixed-instruments-demo", config=config, cell_log=False) as exp:
    sim = exp.add(SimulatedInstrument, "bench")
    print(f"Added: {sim.name} ({type(sim).__name__})")

    try:
        exp.add(Lockin, "lockin", "tcp://localhost:29170", timeout=2.0)
    except Exception as e:
        print(f"Lockin not added — expected without real hardware: {e}")

    print(f"Instruments on this Experiment: {list(exp.instruments)}")

print("\nDone.")
