"""FLEX demo: serve a simulated station, no hardware and no config needed.

Terminal 1 (from the repo root):

    uv run python tests/demo_server.py

Terminal 2 — pick any of:

    uv run flex monitor --follow --address tcp://localhost:29500
    uv run flex monitor bench.x
    uv run python -c "import flex; s = flex.connect('tcp://localhost:29500'); print(s.bench.idn()); s.bench.gate(0.5); print(s.bench.gate())"

Data root is the real one (%LOCALAPPDATA%/flex/data), so `flex monitor`
reads the same DB the server logs to.
"""

from flex.instrument import Numbers, SimulatedInstrument
from flex.server import StationServer
from flex.station import Station

sim = SimulatedInstrument("bench")
sim.add_sim_parameter("x", initial=3.14, unit="V")
sim.add_sim_parameter("gate", unit="V", vals=Numbers(-5, 5))

station = Station({"bench": sim}, name="demo")
server = StationServer(station, port=29500, monitor={"bench": (["x"], 2.0)})
print(f"Serving station '{station.name}' on port {server.port} "
      f"(events on {server.pub_port}), logging bench.x every 2 s. Ctrl-C to stop.")
server.run()
station.close()
