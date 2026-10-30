"""Fails on purpose after a few points, to see how errors show up."""

import time


def run(station, fail_after=3):
    for i in range(10):
        if i == fail_after:
            raise RuntimeError("lock-in lost its reference")
        print(f"point {i + 1}", flush=True)
        time.sleep(0.3)
