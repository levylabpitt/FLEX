"""Lock-in response vs PPMS temperature.

Sets the lock-in excitation, steps the PPMS through a list of temperatures,
waits at each until it has settled, and records X and Y. Data goes to the
usual FLEX experiment/measurement files on the runner's PC.

Run probe.py first to see the formats your lock-in and PPMS actually return.
"""

import time

from flex import Experiment


def run(station, ai_channel=1, ao_channel=1, amplitude=0.01, frequency=13.0,
        start=300.0, stop=295.0, points=3, rate=10.0,
        tolerance=0.5, settle=5.0, timeout=600.0, poll=1.0, user="", notify=False):
    lockin, ppms = station.lockin, station.ppms
    setpoints = [start + (stop - start) * i / max(points - 1, 1) for i in range(points)]

    def settled(setpoint):
        reading = ppms.get_temperature_status()
        return reading["status"] == "Stable" and abs(reading["temperature"] - setpoint) <= tolerance

    def go_to(setpoint):
        ppms.set_temperature(setpoint, rate)
        began, stable_since = time.monotonic(), None
        while True:
            if settled(setpoint):
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= settle:
                    return
            else:
                stable_since = None
            if time.monotonic() - began > timeout:
                raise TimeoutError(f"PPMS did not settle at {setpoint} K within {timeout:.0f} s")
            time.sleep(poll)

    result = {"T": [], "X": [], "Y": []}
    with Experiment(user, name="lock-in vs temperature", notify=notify) as exp:
        exp.add_instrument(lockin)
        exp.add_instrument(ppms)
        lockin.set_ao_function(ao_channel, "Sine")
        lockin.set_ao_frequency(ao_channel, frequency)
        lockin.set_ao_amplitude(ao_channel, amplitude)
        if lockin.get_state() == "idle":
            lockin.set_state("start")
        try:
            with exp.measurement("lock-in vs T") as m:
                for column, unit in (("T_set", "K"), ("T", "K"), ("X", "V"), ("Y", "V")):
                    m.declare(column, unit)
                for setpoint in setpoints:
                    print(f"going to {setpoint:.2f} K", flush=True)
                    go_to(setpoint)
                    t = ppms.get_temperature()
                    xy = lockin.get_lockin_results(ai_channel, ("X", "Y"))
                    m.add_row(T_set=setpoint, T=t, **xy)
                    result["T"].append(t)
                    result["X"].append(xy["X"])
                    result["Y"].append(xy["Y"])
                    print(f"T={t:.3f} K  X={xy['X']}  Y={xy['Y']}", flush=True)
        finally:
            lockin.set_ao_amplitude(ao_channel, 0)
    return result
