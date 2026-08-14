"""FLEX demo: serve a simulated station, no hardware and no config needed.

Terminal 1 (from the repo root):

    uv run python tests/demo_server.py

Then any of:

    uv run flex dashboard                  # Station tab: live panels + spectrum plot
    uv run flex monitor --follow --address tcp://localhost:29500
    uv run flex monitor bench.x
    uv run python -c "import flex; s = flex.connect('tcp://localhost:29500'); print(s.bench.idn()); s.bench.gate(0.5); print(s.bench.gate())"

The "spectrometer" is a SimulatedInstrument with a synthetic drifting
spectrum, so the dashboard's live plot has something to show. Data root is
the real one (%LOCALAPPDATA%/flex/data), so `flex monitor` reads the same
DB the server logs to.
"""

import time

import numpy as np

from flex.instrument import Numbers, SimulatedInstrument
from flex.server import StationServer
from flex.station import Station

sim = SimulatedInstrument("bench")
sim.add_sim_parameter("x", initial=3.14, unit="V")
sim.add_sim_parameter("gate", unit="V", vals=Numbers(-5, 5))

spec = SimulatedInstrument("spectrometer")
_wl = np.linspace(400, 700, 300)
_rng = np.random.default_rng()


def _fake_spectrum():
    peak = 550 + 15 * np.sin(time.time() / 3)
    return 1000 * np.exp(-((_wl - peak) ** 2) / 300) + _rng.normal(0, 15, _wl.size)


spec.add_parameter("spectrum", getter=_fake_spectrum, unit="counts",
                   doc="Synthetic drifting gaussian + noise")

station = Station({"bench": sim, "spectrometer": spec}, name="demo")
server = StationServer(station, port=29500,
                       monitor={"bench": (["x"], 2.0), "spectrometer": (["spectrum"], 1.0)})
print(f"Serving station '{station.name}' on port {server.port} "
      f"(events on {server.pub_port}), logging bench.x @2s and "
      "spectrometer.spectrum @1s. Ctrl-C to stop.")
server.run()
station.close()
