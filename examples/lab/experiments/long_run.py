"""Runs for a while, so you can try Abort. The finally block must still run."""

import time


def run(station, seconds=60):
    station.bench.gate(2.0)
    print("gate set to 2.0 V", flush=True)
    try:
        for i in range(int(seconds)):
            print(f"{i + 1}/{int(seconds)} s", flush=True)
            time.sleep(1)
    finally:
        station.bench.gate(0)
        print("cleaned up: gate back to 0 V", flush=True)
