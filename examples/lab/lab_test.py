import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="FLEX Lab Test")


@app.cell
def _():
    import html
    import json
    import os
    import subprocess
    import sys
    import tempfile
    import time
    from pathlib import Path

    import marimo as mo

    HERE = Path(__file__).parent
    LAB = Path(tempfile.gettempdir()) / "flex-lab-test"
    return HERE, LAB, html, json, mo, os, subprocess, sys, time


@app.cell
def _(mo):
    mo.md(r"""
    # FLEX lab test

    A simulated two-PC lab (no hardware): **PC A** has a `bench` (gate → x), **PC B** a
    `spectrometer`, and one runner controls both. Things to try, top to bottom:

    1. **Direct access** – move the slider, `bench.x` follows; read the spectrometer.
    2. **Run `gate_sweep`** → `done`, with a plot.
    3. **Run `two_pcs`** → `done`, one script driving both PCs.
    4. **Run `long_run`, press Abort** → `aborted`, and the log shows `cleaned up`.
    5. **Run `failing`** → `failed`, with the error and traceback.
    6. **Press Run while another run is going** → refused as busy.
    7. **Start `long_run`, close this window, double-click the launcher again** → the run is still going.
    """)
    return


@app.cell
def _(HERE, LAB, mo, os, subprocess, sys, time):
    from flex.client import StationGroup
    from flex.runner import RunClient

    RUNNER = "tcp://127.0.0.1:29610"
    PC_A, PC_B = "tcp://127.0.0.1:29600", "tcp://127.0.0.1:29602"

    def _runner_up():
        try:
            RunClient(RUNNER, timeout=1.0).close()
            return True
        except Exception:
            return False

    if not _runner_up():
        LAB.mkdir(exist_ok=True)
        _stack = str(HERE / "lab_stack.py")
        if os.name == "nt":
            # via PowerShell, so the stack is not a child of this notebook and
            # survives the notebook's process tree being killed
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Start-Process -WindowStyle Hidden -FilePath '{sys.executable}' -ArgumentList '\"{_stack}\"'"],
                check=True,
            )
        else:
            subprocess.Popen([sys.executable, _stack], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if _runner_up():
                break
            time.sleep(0.5)

    mo.stop(
        not _runner_up(),
        mo.callout(mo.md(f"The test stack did not start. See `{LAB / 'stack.log'}`."), kind="danger"),
    )
    client = RunClient(RUNNER, timeout=3.0)
    group = StationGroup([PC_A, PC_B], timeout=3.0)
    stop_stack = mo.ui.run_button(label="Stop test stack", kind="danger")
    mo.hstack([mo.md("**Test stack is running** (a separate background process)"), stop_stack],
              justify="space-between")
    return client, group, stop_stack


@app.cell
def _(LAB, mo, stop_stack):
    mo.stop(not stop_stack.value)
    (LAB / "stop").touch()
    mo.callout(mo.md("Stopping. Close this window; the next launch starts a fresh stack."), kind="warn")
    return


@app.cell
def _(html, mo):
    def svg_plot(xs, ys, xlabel="", ylabel="", w=560, h=260):
        pad = 62
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

        def sx(v):
            return pad + (v - x0) / ((x1 - x0) or 1) * (w - 2 * pad)

        def sy(v):
            return h - pad - (v - y0) / ((y1 - y0) or 1) * (h - 2 * pad)

        pts = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(xs, ys, strict=True))
        dots = "".join(f'<circle cx="{sx(a):.1f}" cy="{sy(b):.1f}" r="3" fill="#2563eb"/>'
                       for a, b in zip(xs, ys, strict=True)) if len(xs) < 60 else ""
        txt = 'fill="currentColor" font-size="11" opacity="0.7"'
        return mo.Html(
            f'<svg viewBox="0 0 {w} {h}" width="{w}" style="max-width:100%">'
            f'<rect x="{pad}" y="{pad // 2}" width="{w - 2 * pad}" height="{h - 1.5 * pad}" '
            f'fill="none" stroke="currentColor" opacity="0.25"/>'
            f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="2"/>{dots}'
            f'<text x="{pad}" y="{h - pad + 16}" {txt}>{x0:.3g}</text>'
            f'<text x="{w - pad}" y="{h - pad + 16}" text-anchor="end" {txt}>{x1:.3g}</text>'
            f'<text x="{w / 2}" y="{h - 8}" text-anchor="middle" {txt}>{html.escape(xlabel)}</text>'
            f'<text x="{pad - 6}" y="{h - pad}" text-anchor="end" {txt}>{y0:.3g}</text>'
            f'<text x="{pad - 6}" y="{pad // 2 + 8}" text-anchor="end" {txt}>{y1:.3g}</text>'
            f'<text x="12" y="{h / 2}" {txt} transform="rotate(-90 12 {h / 2})" '
            f'text-anchor="middle">{html.escape(ylabel)}</text></svg>'
        )

    return (svg_plot,)


@app.cell
def _(mo):
    mo.md("""
    ## 1. Direct access
    No runner involved: this notebook talks to the instrument servers like the dashboard does.
    """)
    return


@app.cell
def _(mo):
    gate_slider = mo.ui.slider(-2, 2, 0.1, value=0, label="bench.gate (V)", full_width=True)
    gate_slider
    return (gate_slider,)


@app.cell
def _(gate_slider, group, mo):
    group.bench.gate(gate_slider.value)
    mo.md(f"gate = **{gate_slider.value:g} V** → `bench.x` = **{group.bench.x():.4f} V**")
    return


@app.cell
def _(mo):
    read_spectrum = mo.ui.run_button(label="Read spectrometer")
    read_spectrum
    return (read_spectrum,)


@app.cell
def _(group, mo, read_spectrum, svg_plot):
    mo.stop(not read_spectrum.value)
    _y = group.spectrometer.spectrum()
    svg_plot(list(range(len(_y))), _y, "pixel", "counts")
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2. Run an experiment
    Pick a script, edit it or its params if you like, and press Run.
    The runner executes it, not this notebook.
    """)
    return


@app.cell
def _(HERE, mo):
    scripts = {p.stem: p for p in sorted((HERE / "experiments").glob("*.py"))}
    script_choice = mo.ui.dropdown(list(scripts), value="gate_sweep", label="Experiment")
    script_choice
    return script_choice, scripts


@app.cell
def _(mo, script_choice, scripts):
    _defaults = {"gate_sweep": '{"points": 11}', "two_pcs": '{"points": 8}',
                 "long_run": '{"seconds": 60}', "failing": '{"fail_after": 3}'}
    code_editor = mo.ui.code_editor(scripts[script_choice.value].read_text(encoding="utf-8"),
                                    language="python", min_height=220)
    params_text = mo.ui.text(_defaults.get(script_choice.value, "{}"), label="Params (JSON)", full_width=True)
    run_button = mo.ui.run_button(label="Run", kind="success")
    abort_button = mo.ui.run_button(label="Abort", kind="danger")
    refresh = mo.ui.refresh(options=["1s", "2s", "5s"], default_interval="1s")
    mo.vstack([code_editor, params_text, mo.hstack([run_button, abort_button, refresh], justify="start")])
    return abort_button, code_editor, params_text, refresh, run_button


@app.cell
def _(mo):
    get_run, set_run = mo.state(None)
    return get_run, set_run


@app.cell
def _(
    client,
    code_editor,
    json,
    mo,
    params_text,
    run_button,
    script_choice,
    set_run,
):
    mo.stop(not run_button.value)
    try:
        _rec = client.submit(code_editor.value, params=json.loads(params_text.value or "{}"),
                             name=script_choice.value)
    except Exception as _e:
        _out = mo.callout(mo.md(f"**Could not start:** {_e}"), kind="danger")
    else:
        set_run(_rec["id"])
        _out = mo.callout(mo.md(f"Started `{_rec['id']}`"), kind="success")
    _out
    return


@app.cell
def _(abort_button, client, mo):
    mo.stop(not abort_button.value)
    try:
        client.abort()
        _out = mo.callout(mo.md("Abort requested."), kind="warn")
    except Exception as _e:
        _out = mo.callout(mo.md(f"**Could not abort:** {_e}"), kind="danger")
    _out
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3. Status
    """)
    return


@app.cell
def _(client, get_run, html, mo, refresh, svg_plot, time):
    refresh
    _id = get_run()
    mo.stop(_id is None, mo.md("_No run submitted yet._"))
    _rec = client.run(_id)
    _kinds = {"running": "info", "done": "success", "failed": "danger", "aborted": "warn", "interrupted": "warn"}
    _took = (_rec["finished"] or time.time()) - _rec["started"]
    _head = mo.callout(
        mo.md(f"**{_rec['status']}** · `{_rec['id']}` · {_rec['name']} · {_took:.0f}s"
              + (f"<br>{html.escape(_rec['error'])}" if _rec["error"] else "")),
        kind=_kinds.get(_rec["status"], "neutral"),
    )
    _log = mo.Html("<pre style='max-height:260px;overflow:auto;font-size:12px'>"
                   + html.escape("\n".join(_rec["log"][-60:])) + "</pre>")
    _parts = [_head, _log]
    _res = _rec["result"]
    if isinstance(_res, dict) and "gate" in _res:
        for _key in [k for k in _res if k != "gate"]:
            _parts.append(svg_plot(_res["gate"], _res[_key], "gate (V)", _key))
    mo.vstack(_parts)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. History
    """)
    return


@app.cell
def _(client, mo, refresh, time):
    refresh
    _rows = [
        {"run": r["id"], "name": r["name"], "status": r["status"],
         "started": time.strftime("%H:%M:%S", time.localtime(r["started"])),
         "took (s)": round((r["finished"] or time.time()) - r["started"])}
        for r in client.runs(15)
    ]
    mo.ui.table(_rows, selection=None) if _rows else mo.md("_No runs yet._")
    return


if __name__ == "__main__":
    app.run()
