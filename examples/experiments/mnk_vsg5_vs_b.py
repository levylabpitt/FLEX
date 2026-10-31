"""MNK: Vsg5 sweeps (fast axis) at each magnetic field (slow axis).

At every field the Transport Server runs one lock-in sweep of the SG5 gate and
writes the curve to its own experiment folder. This script steps the magnet and
keeps a FLEX record of the field each curve was taken at.
"""

import time
from contextlib import suppress

from flex import Experiment

WIRING = """\
     #                CC            KH                  @Voltage

    I+/-:             2/7           2/6                 @ 800uV ac amp+ 0mv dc  from ch2
    V+/-:             3/8           3/7
    Vbg:               11             4                  @ -19V
    Vsg9:              9              8                  @ 0
    Vsg5:               5             5                  @ 0 to 2.6v up-down is fast axis
    Vsg1:              28             1                  @ 0

    T=16mK"""


def run(station, folder="48-SweepVsg5_B_0T_to_18T",
        b_start=0.0, b_end=18.0, b_step=0.1, b_rate=1.0, b_tol=0.001,
        sg_channel=5, sg_start=0.0, sg_end=2.6, sg_time=120.0, sg_wait=1.0,
        field_timeout=600.0, sweep_timeout=120.0, poll=1.0, user="", notify=False):
    magnet, transport = station.magnet, station.transport

    steps = round(abs(b_end - b_start) / b_step)
    fields = [b_start + (b_end - b_start) * i / steps for i in range(steps + 1)] if steps else [b_start]
    sweep = {
        "sweepTime": sg_time,
        "initialWaitTime": sg_wait,
        "returnToStart": False,
        "sweepChannels": [{"Enable?": True, "Channel": sg_channel, "Start": sg_start,
                           "End": sg_end, "Pattern": "Ramp /\\", "Table": []}],
    }
    comment = (f"\n{WIRING}\n    B={b_start:g} to {b_end:g} T in steps of {b_step:g} T is slow axis"
               f"\n    Sweep time={sg_time:g} s\n    Total curves={len(fields)}")

    def go_to_field(field):
        magnet.set_magnet(field, b_rate)
        began = time.monotonic()
        while abs(field - (now := magnet.get_field())) > b_tol:
            if time.monotonic() - began > field_timeout:
                raise TimeoutError(f"Magnet did not reach {field} T within {field_timeout:.0f} s")
            time.sleep(poll)
        return now

    def sweep_once():
        # started without blocking, and waited for here: a blocking driver call would hold
        # the transport's worker, so an abort could not reach it to stop the sweep
        transport.lockin_sweep(folder, comment, sweep, run_async=True)
        time.sleep(sg_time + sg_wait)
        began = time.monotonic()
        while transport.get_status() != "idle":
            if time.monotonic() - began > sweep_timeout:
                raise TimeoutError(f"Transport still busy {sweep_timeout:.0f} s after the sweep time")
            time.sleep(poll)

    measured = []
    with Experiment(user, name="MNK Vsg5 vs B", notify=notify, cell_log=False) as exp:
        exp.add_instrument(magnet)
        exp.add_instrument(transport)
        exp.note(f"{folder}{comment}")
        try:
            with exp.measurement("Vsg5 sweeps vs B") as m:
                m.declare("B_set", "T")
                m.declare("B", "T")
                for n, field in enumerate(fields, 1):
                    reached = go_to_field(field)
                    print(f"[{n}/{len(fields)}] Vsg5 sweep at B={reached:.3f} T", flush=True)
                    sweep_once()
                    m.add_row(B_set=field, B=reached)
                    measured.append(reached)
        except BaseException:
            with suppress(Exception):  # the app would otherwise finish the sweep on its own
                transport.stop_transport()
            raise
    return {"B": measured}
