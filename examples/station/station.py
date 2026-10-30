import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="FLEX Station")


@app.cell
def _():
    import html
    import json
    import time
    from pathlib import Path

    import marimo as mo

    EXPERIMENTS = Path(__file__).parent.parent / "experiments"
    return EXPERIMENTS, html, json, mo, time


@app.cell
def _(mo):
    mo.md("""
    # FLEX station

    This PC's lock-in and PPMS, driven through the station server and the runner.

    1. **Read instruments** to see the lock-in and PPMS answering.
    2. **Run `probe`** and read the log: it shows exactly what each call returns. Nothing is set.
    3. **Run `lockin_vs_temperature`**. Keep `points` small the first time.
    """)
    return


@app.cell
def _(mo):
    from flex.client import StationGroup
    from flex.config import load_config
    from flex.runner import RunClient

    _cfg = load_config()
    _servers = _cfg.runner.servers or [f"tcp://127.0.0.1:{_cfg.server.port}"]
    try:
        client = RunClient(f"tcp://127.0.0.1:{_cfg.runner.port}", timeout=3.0, token=_cfg.runner.token)
        group = StationGroup(_servers, timeout=5.0)
    except Exception as _e:
        mo.stop(True, mo.callout(
            mo.md(f"**Station not reachable:** {_e}<br>Start it with `Start FLEX Station.bat` "
                  "(`flex serve` must be running)."), kind="danger"))
    mo.md(f"Connected: station **{group.name}**, instruments **{', '.join(group.instruments) or 'none'}**")
    return client, group


@app.cell
def _(mo):
    read_button = mo.ui.run_button(label="Read instruments")
    read_button
    return (read_button,)


@app.cell
def _(group, mo, read_button):
    mo.stop(not read_button.value)
    _rows = []
    for _name, _inst in group.instruments.items():
        for _pname, _param in _inst.parameters.items():
            if _param.gettable:
                try:
                    _value = repr(_param.get())
                except Exception as _e:
                    _value = f"FAILED: {_e}"
                _rows.append({"instrument": _name, "parameter": _pname, "value": _value, "unit": _param.unit})
    mo.ui.table(_rows, selection=None) if _rows else mo.md("_No readable parameters._")
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
            f'<text x="{pad - 6}" y="{h - pad}" text-anchor="end" {txt}>{y0:.4g}</text>'
            f'<text x="{pad - 6}" y="{pad // 2 + 8}" text-anchor="end" {txt}>{y1:.4g}</text>'
            f'<text x="12" y="{h / 2}" {txt} transform="rotate(-90 12 {h / 2})" '
            f'text-anchor="middle">{html.escape(ylabel)}</text></svg>'
        )

    return (svg_plot,)


@app.cell
def _(EXPERIMENTS, mo):
    scripts = {p.stem: p for p in sorted(EXPERIMENTS.glob("*.py"))}
    script_choice = mo.ui.dropdown(list(scripts), value="probe", label="Experiment")
    script_choice
    return script_choice, scripts


@app.cell
def _(mo, script_choice, scripts):
    _defaults = {"lockin_vs_temperature": '{"points": 3}'}
    code_editor = mo.ui.code_editor(scripts[script_choice.value].read_text(encoding="utf-8"),
                                    language="python", min_height=220)
    params_text = mo.ui.text(_defaults.get(script_choice.value, "{}"), label="Params (JSON)", full_width=True)
    run_button = mo.ui.run_button(label="Run", kind="success")
    abort_button = mo.ui.run_button(label="Abort", kind="danger")
    refresh = mo.ui.refresh(options=["1s", "2s", "5s"], default_interval="2s")
    mo.vstack([code_editor, params_text, mo.hstack([run_button, abort_button, refresh], justify="start")])
    return abort_button, code_editor, params_text, refresh, run_button


@app.cell
def _(mo):
    get_run, set_run = mo.state(None)
    return get_run, set_run


@app.cell
def _(client, code_editor, json, mo, params_text, run_button, script_choice, set_run):
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
    _log = mo.Html("<pre style='max-height:420px;overflow:auto;font-size:12px'>"
                   + html.escape("\n".join(_rec["log"][-200:])) + "</pre>")
    _parts = [_head, _log]
    _res = _rec["result"]
    if isinstance(_res, dict) and len(_res) > 1 and all(isinstance(v, list) and v for v in _res.values()):
        _xkey, *_ykeys = list(_res)
        for _key in _ykeys:
            try:
                _parts.append(svg_plot(_res[_xkey], _res[_key], _xkey, _key))
            except (TypeError, ValueError):
                pass  # e.g. None values from an unexpected reply format; the log shows them
    mo.vstack(_parts)
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
