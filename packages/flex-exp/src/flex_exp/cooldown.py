"""Cooldown: ramp the PPMS to a target temperature, logging a lock-in channel ratio against it.

A runner script: ``from flex_exp.cooldown import cooldown as run``. What runs is the code installed on
the PC; whoever submits it (a notebook, the hub's cooldown app) only chooses the parameters, and the
limits below are checked here whatever they send. Each reading is printed as a ``DATA {json}`` line
for live plots (``flex.marimo.data_rows``); the full table goes to the usual experiment files.
"""

from __future__ import annotations

import json
import math
import time

from flex_exp.experiment import Experiment

TEMPERATURE = (1.8, 400.0)  # K, allowed targets
RATE = (0.01, 12.0)  # K/min
MAX_AMPLITUDE = 0.1  # V of lock-in excitation
MIN_INTERVAL = 0.2  # s between readings
TOLERANCE = 0.2  # K from the target that counts as arrived
SETTLE = 10.0  # s the PPMS must stay stable at the target before the run ends


def _check(name: str, value: float, low: float, high: float) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} {value:g} is outside the allowed range {low:g} to {high:g}")


def cooldown(station, numerator: int, denominator: int, target: float, rate: float, *,
             amplitude: float = 0.01, frequency: float = 13.0, ao_channel: int = 1,
             interval: float = 2.0, user: str = "", sample: str = "", notify: bool = False) -> dict:
    """Ramp ``station.ppms`` down to ``target`` K at ``rate`` K/min, recording T and the ratio of the
    lock-in X on channel ``numerator`` over channel ``denominator``. The PPMS ramps by itself, so an
    aborted or failed run leaves it still ramping: that is said in the log."""
    lockin, ppms = station.lockin, station.ppms
    _check("Target", target, *TEMPERATURE)
    _check("Rate", rate, *RATE)
    if not 0 < amplitude <= MAX_AMPLITUDE:
        raise ValueError(f"Amplitude {amplitude:g} V must be above 0 and at most {MAX_AMPLITUDE:g} V")
    if numerator == denominator:
        raise ValueError("Numerator and denominator must be different channels")
    if interval < MIN_INTERVAL:
        raise ValueError(f"Interval must be at least {MIN_INTERVAL:g} s")
    start = ppms.get_temperature()
    if target >= start - TOLERANCE:
        raise ValueError(f"A cooldown needs a target below the current temperature ({start:.2f} K)")
    limit = (start - target) / rate * 60 * 1.5 + 600  # s: the ramp plus half again, plus slack

    completed = False
    with Experiment(user, name=f"cooldown {sample}".strip(), notify=notify) as exp:
        exp.add_instrument(lockin)
        exp.add_instrument(ppms)
        lockin.set_ao_function(ao_channel, "Sine")
        lockin.set_ao_frequency(ao_channel, frequency)
        lockin.set_ao_amplitude(ao_channel, amplitude)
        if lockin.get_state() == "idle":
            lockin.set_state("start")
        print(f"cooldown {start:.2f} K -> {target:g} K at {rate:g} K/min, G = X(ch {numerator}) / X(ch {denominator})",
              flush=True)
        try:
            with exp.measurement("cooldown") as m:
                for column, unit in (("t", "s"), ("T", "K"), ("G", ""), ("X_num", "V"), ("Y_num", "V"),
                                     ("X_den", "V"), ("Y_den", "V")):
                    m.declare(column, unit)
                ppms.set_temperature(target, rate)
                began, arrived, last = time.monotonic(), None, {}
                while True:
                    elapsed = time.monotonic() - began
                    reading = ppms.get_temperature_status()
                    num = lockin.get_lockin_results(numerator, ("X", "Y"))
                    den = lockin.get_lockin_results(denominator, ("X", "Y"))
                    temperature = reading["temperature"]
                    g = num["X"] / den["X"] if num["X"] is not None and den["X"] else None
                    m.add_row(t=elapsed, T=temperature, G=math.nan if g is None else g,
                              X_num=num["X"], Y_num=num["Y"], X_den=den["X"], Y_den=den["Y"])
                    last = {"t": round(elapsed, 1), "T": temperature, "G": g}
                    print("DATA " + json.dumps(last), flush=True)
                    if reading["status"] == "Stable" and abs(temperature - target) <= TOLERANCE:
                        arrived = arrived or time.monotonic()
                        if time.monotonic() - arrived >= SETTLE:
                            break
                    else:
                        arrived = None
                    if elapsed > limit:
                        raise TimeoutError(f"The PPMS did not reach {target:g} K within {limit / 60:.0f} min")
                    time.sleep(interval)
            completed = True
        finally:
            lockin.set_ao_amplitude(ao_channel, 0)
            if not completed:
                print(f"WARNING: stopped before reaching {target:g} K. The PPMS is still ramping to {target:g} K at "
                      f"{rate:g} K/min; stop it from the PPMS PC.", flush=True)
    return {"points": m.rows, "T": last["T"], "G": last["G"], "seconds": last["t"]}
