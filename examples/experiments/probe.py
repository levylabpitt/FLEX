"""Read-only check of the lock-in and PPMS: prints exactly what each call returns.

Run this first against a new station. It sets nothing.
"""


def run(station, lockin_channel=1):
    def show(label, fn, *args):
        try:
            print(f"{label}: {fn(*args)!r}", flush=True)
        except Exception as e:
            print(f"{label}: FAILED {type(e).__name__}: {e}", flush=True)

    print("instruments:", ", ".join(station.instruments), flush=True)
    for name, inst in station.instruments.items():
        show(f"{name}.idn()", inst.idn)
        for pname, param in inst.parameters.items():
            if param.gettable:
                show(f"{name}.{pname}", param.get)

    if "lockin" in station.instruments:
        li = station.lockin
        show("lockin.get_state()", li.get_state)
        show(f"lockin.get_ai({lockin_channel})", li.get_ai, lockin_channel)
        show(f"lockin.get_ao({lockin_channel})", li.get_ao, lockin_channel)
        for quantity in ("X", "Y", "R", "Theta"):
            show(f"lockin.get_lockin_result({lockin_channel}, {quantity!r})", li.get_lockin_result,
                 lockin_channel, quantity)
        show("lockin.get_results() keys",
             lambda: [row["key"] for row in li.get_results()["Results (Dictionary)"]])

    if "ppms" in station.instruments:
        pp = station.ppms
        show("ppms.get_temperature()", pp.get_temperature)
        show("ppms.get_temperature_target()", pp.get_temperature_target)
        show("ppms.get_magnet()", pp.get_magnet)
        show("ppms.get_magnet_target()", pp.get_magnet_target)
        show("ppms.get_lhe_level()", pp.get_lhe_level)
