"""A simulated two-PC lab for trying the runner: no hardware, no config.

"PC A" serves a bench (gate -> x), "PC B" serves a spectrometer, and one
runner controls both. Started by lab_test.py; runs until stopped from there
(or until the file `stop` appears next to the temp data).
"""

import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from flex.instrument import Numbers, SimulatedInstrument
from flex.runner import RunServer
from flex.server import StationServer
from flex.station import Station

LAB = Path(tempfile.gettempdir()) / "flex-lab-test"
PC_A, PC_B, RUNNER = 29600, 29602, 29610
LAB.mkdir(exist_ok=True)
sys.stdout = sys.stderr = open(LAB / "stack.log", "w", buffering=1)  # nobody is watching a console
rng = np.random.default_rng()

bench = SimulatedInstrument("bench")
bench.add_sim_parameter("gate", unit="V", vals=Numbers(-5, 5))
bench.add_parameter("x", getter=lambda: float(np.sin(3 * bench.values["gate"]) + rng.normal(0, 0.02)), unit="V")

spectrometer = SimulatedInstrument("spectrometer")
wavelengths = np.linspace(400, 700, 300)


def spectrum():
    peak = 550 + 15 * np.sin(time.time() / 3)
    return 1000 * np.exp(-((wavelengths - peak) ** 2) / 300) + rng.normal(0, 15, wavelengths.size)


spectrometer.add_parameter("spectrum", getter=spectrum, unit="counts")

station_a = Station({"bench": bench}, name="pc-a")
station_b = Station({"spectrometer": spectrometer}, name="pc-b")
servers = [StationServer(station_a, port=PC_A), StationServer(station_b, port=PC_B)]
runner = RunServer([f"tcp://127.0.0.1:{PC_A}", f"tcp://127.0.0.1:{PC_B}"], root=LAB / "runs", port=RUNNER)

stop = LAB / "stop"
stop.unlink(missing_ok=True)
for s in servers:
    s.start()
runner.start()
print("lab stack ready", flush=True)
try:
    while not stop.exists():
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
runner.stop()
for s in servers:
    s.stop()
station_a.close()
station_b.close()
print("lab stack stopped", flush=True)
