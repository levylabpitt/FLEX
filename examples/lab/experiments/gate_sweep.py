"""Sweep the bench gate and read x. Finishes in a few seconds."""

import time


def run(station, start=0.0, stop=1.0, points=11, delay=0.2):
    gates, xs = [], []
    try:
        for i in range(points):
            gate = start + (stop - start) * i / max(points - 1, 1)
            station.bench.gate(gate)
            gates.append(gate)
            xs.append(station.bench.x())
            print(f"point {i + 1}/{points}: gate={gate:.3f} x={xs[-1]:.4f}", flush=True)
            time.sleep(delay)
    finally:
        station.bench.gate(0)
    return {"gate": gates, "x": xs}
