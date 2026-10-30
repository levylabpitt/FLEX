"""One experiment driving two PCs: the bench (PC A) and the spectrometer (PC B)."""

import time


def run(station, start=0.0, stop=1.0, points=8, delay=0.3):
    gates, xs, peaks = [], [], []
    try:
        for i in range(points):
            gate = start + (stop - start) * i / max(points - 1, 1)
            station.bench.gate(gate)
            spectrum = station.spectrometer.spectrum()
            gates.append(gate)
            xs.append(station.bench.x())
            peaks.append(max(spectrum))
            print(f"point {i + 1}/{points}: gate={gate:.3f} x={xs[-1]:.4f} peak={peaks[-1]:.0f}", flush=True)
            time.sleep(delay)
    finally:
        station.bench.gate(0)
    return {"gate": gates, "x": xs, "peak": peaks}
