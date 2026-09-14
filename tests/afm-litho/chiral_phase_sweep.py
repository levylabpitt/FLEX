"""Chiral phase sweep: write the base circuit, then write / measure / erase the
chiral wire at 90, 45, 0, -45, -90 degrees of phase.

Runs against afm-litho `main` (absolute setpoint; `readDeflection` is not on
main yet, so the free-air read comes from `getTelemetry` while withdrawn) and
flex-afm `main` (7b17121, FLEX v1.1.0 drivers).

AFM verbs go to afm-litho (29180); lock-in and Krohn-Hite calls go straight to
their own FLEX drivers (29170 / 29160). Nothing is routed through the AFM.
"""

#%%
from __future__ import annotations

import logging
import time
from pathlib import Path
import math
from contextlib import contextmanager
from typing import Literal, Iterator

from flex.inst.levylab.Lockin import Lockin
from flex.inst.levylab.Krohn_Hite_7008 import Krohn_Hite_7008
from flex.inst.levylab import AFMLitho
from flex.inst.levylab.TransportServer import Transport
    

# ---------------------------------------------------------------- preamble
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("chiral_phase_sweep")

SVG = Path(__file__).with_name("chiral_sweep.svg")
OUT = Path(__file__).with_name("chiral_phase_sweep_out")
OUT.mkdir(exist_ok=True)

FUNNELS = ["path3768", "path3768-3", "path9", "path9-11"]
LEADS = ["path4-9-5", "path4", "path7", "path5"]
CHIRAL = "chiral-target"
ERASE = "erase"

PHASES_DEG = [90, 45, 0, -45, -90]
AMP_GAIN = 25.0
# Lock-in monitoring: channel 1 drives 0.1 V, channel 2 is read back.
EXCITATION_V = 0.1
EXCITATION_HZ = 13.0
DRIVE_CH, READ_CH = 1, 2
POLL_S = 0.2

# There is no "segments" property; a funnel fill is set by its line spacing.
# The funnel mouths in this SVG are ~4-6 um wide, so 20 lines ~ 0.25 um.
FUNNEL_FILL_SPACING_UM = 0.5

afm = AFMLitho("tcp://localhost:29180")
lockin = Lockin("tcp://localhost:29170")
kh = Krohn_Hite_7008("tcp://localhost:29160")
transport = Transport()
print(afm.idn())

def run_iv(exp_folder, exp_comment, sweep_time, channel, start, stop, sweep_function='Ramp /', sweep_table = [], initial_wait = 1):
    sweep_config = {
        'sweepTime': sweep_time,
        'initialWaitTime': initial_wait,
        'returnToStart': False,
        'sweepChannels': [{
                'Enable?': True,
                'Channel': channel,
                'Start': start,
                'End': stop,
                'Pattern': sweep_function,
                'Table': sweep_table,
                        }],
    }
    transport.LockinSweep(expt_folder=exp_folder, expt_comments=exp_comment, sweep_config=sweep_config)

@contextmanager
def monitor_conductance(exp_folder: str, exp_comment: str) -> Iterator[None]:
    transport.setExptFolder(exp_folder)
    transport.setExptComments(exp_comment)
    transport.setRefreshTime(2000)
    transport.startTransport("LockinTime")
    try:
        yield
    finally:
        transport.stopTransport()
        while transport.getStatus() != 'idle':
            pass

# def monitor_conductance(action: Literal["start", "stop"], exp_folder: str, exp_comment: str) -> None:
#     if action == "start":
#         transport.setExptFolder(exp_folder)
#         transport.setExptComments(exp_comment)
#         transport.startTransport("LockinTime")
#     elif action == "stop":
#         transport.stopTransport("LockinTime")
#     else:
#         raise ValueError(f"Invalid action {action!r}. Expected 'start' or 'stop'.")

def write_watching(object_id: str) -> tuple[float | None, float | None, list]:
    """Start a write and poll conductance until it finishes. The heartbeat
    thread keeps the control token alive while this thread polls."""
    trace: list[tuple[float, float | None]] = []
    with afm.heartbeat_context():
        afm.start_write(objects=[object_id], amp_gain=AMP_GAIN)
        t0 = time.time()
        while afm.get_state() == "writing":
            time.sleep(POLL_S)

#%% - AFM EXPERIMENT
with afm.session("chiral-phase-sweep", deadman_s=60):

    w = afm.withdraw()
    assert w.get("ok"), f"withdraw failed: {w}"
    afm.set_mode("ac")

    scan = afm.scan(size_um=25,
                   pixels=64, 
                   lines=64, 
                   line_rate_hz=1.5, 
                   x_offset_um=0, 
                   y_offset_um=0,
                   engage=True,
                   setpoint=0.65)

    log.info("scan files: %s", scan.get("files"))
    w = afm.withdraw()
    assert w.get("ok"), f"withdraw failed: {w}"

    # ------------------------------------------------ set mode to contact
    # setMode is refused while engaged, so withdraw first, then switch.
    w = afm.withdraw()
    assert w.get("ok"), f"withdraw failed: {w}"
    afm.set_mode("contact")

    # ------------------------ withdraw to make sure we are off the surface
    w = afm.withdraw()
    assert w.get("ok"), f"withdraw failed: {w}"

    # --------------------------------- read the deflection while withdrawn
    free_air_defl = afm.get_telemetry()["defl_v"]
    log.info("free-air deflection %.4f V", free_air_defl)
    afm.approach(setpoint=free_air_defl + 0.1, pgain=0.0, igain=10.0, settle_s=1.0)

    # ------------------------------------------------------- load the file
    listing = afm.load_pattern(SVG.read_text(encoding="utf-8"))
    ids = [o["id"] for o in listing["objects"]]
    print([(o["id"], o["points"]) for o in listing["objects"]])
    log.info("loaded objects: %s", ids)
    for needed in FUNNELS + LEADS + [CHIRAL, ERASE]:
        assert needed in ids, f"{needed} missing from the SVG load"

    # --------------- wires and funnels: 2 um/s, 30 V
    updates = {obj: {"voltage": 10.0, "speed_um_s": 10.0} for obj in LEADS + FUNNELS}
    afm.set_objects(updates)

    # --------------------------- write everything except the chiral segment
    # (and except the erase rectangle, which is not part of the circuit)
    afm.write(objects=FUNNELS + LEADS, amp_gain = AMP_GAIN)

    # -------------- chiral segment: 90 deg, 30 V, 8 V mod, 0.5 um/s, 0.1 um
    afm.set_objects({CHIRAL: {
        "voltage": 0.0, "speed_um_s": 10,
        "chiral": {"lambda_um": 0.5, "y_amp_um": 0.5, "v_k": 10.0,
                   "phase_deg": PHASES_DEG[0], "hand": 1},
    }})

    # erase rectangle: -10 V (set once; reused every phase)
    afm.set_objects({ERASE: {"voltage": -10.0, "speed_um_s": 10.0,
                         "fill": {"spacing_um": 0.075}}})

    results = []
    for phase in PHASES_DEG:
        log.info("==== phase %+d deg ====", phase)
        afm.set_objects({CHIRAL: {"chiral": {"phase_deg": phase}}})

        with monitor_conductance('conmon_CHIRAL', "Conductance measurement"):
            write_watching(CHIRAL)

        # ------------- lift the tip: the IV measures the device, not the tip
        w = afm.withdraw()
        assert w.get("ok"), f"withdraw failed: {w}"
        print("Chiral writing finished for phase: ", phase)
        # Run the IV Measurement
        iv = {"n_points": 0, "path": None}
        log.info("IV sweep: Running via TransportServer")
        run_iv(exp_folder = 'afm_chiral_automation_test',
               exp_comment = f'phase={phase}',
               sweep_time=30,
               channel=5, 
               start=0, 
               stop=0, 
               sweep_function='Table', 
               sweep_table=[0,-0.05,0,0.05,0])

        # ------------------------------ tip back down at the same setpoint
        afm.approach(setpoint=free_air_defl + 0.1, pgain=0.0, igain=10.0, settle_s=1.0)

        # ------------------------------------ monitoring again, then erase

        with monitor_conductance('conmon_ERASE', "Conductance measurement"):
            write_watching(ERASE)

    afm.withdraw()

# session exit released control; withdraw already done above.
afm.close()
