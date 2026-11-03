import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="FLEX cooldown")


@app.cell
def _():
    import html

    import marimo as mo

    import flex.marimo as fm

    return fm, html, mo


@app.cell
def _(fm, mo):
    _names = fm.hosts()
    mo.stop(not _names, mo.callout(mo.md("No stations are configured: add `[hosts.<name>]` to flex.toml."), kind="danger"))
    host = mo.ui.dropdown(_names, value=_names[0], label="Station")
    host
    return (host,)


@app.cell
def _(fm, host, mo):
    try:
        station, runs = fm.connect(host.value)
    except Exception as _e:
        mo.stop(True, mo.callout(mo.md(f"**Cannot reach {host.value}:** {_e}"), kind="danger"))
    _missing = [_n for _n in ("lockin", "ppms", "ce") if _n not in station.instruments]
    mo.stop(bool(_missing), mo.callout(
        mo.md(f"**{host.value} cannot run a cooldown:** it has no {', '.join(_missing)} instrument."), kind="warn"))
    return runs, station


@app.cell
def _(mo, station):
    _wired = station.ce.get_wiring()
    mo.stop(not _wired, mo.callout(mo.md("The Configure Experiments file has no wired channels."), kind="warn"))
    _options = {f"ch {w['channel']} · {w['electrode']} · {w['label']}": w["channel"] for w in _wired}

    def _pick(tag, fallback):
        return next((k for k in _options if tag in k), list(_options)[min(fallback, len(_options) - 1)])

    numerator = mo.ui.dropdown(_options, value=_pick("I-", 0), label="Numerator (I−)")
    denominator = mo.ui.dropdown(_options, value=_pick("I+", 1), label="Denominator (I+)")
    target = mo.ui.number(1.8, 400, step=0.1, value=2.0, label="Target (K)")
    rate = mo.ui.number(0.01, 12, step=0.1, value=1.0, label="Rate (K/min)")
    amplitude = mo.ui.number(0.001, 0.1, step=0.001, value=0.01, label="Excitation (V)")
    frequency = mo.ui.number(1, 1000, step=1, value=13, label="Frequency (Hz)")
    name = mo.ui.text(label="Your name")
    sample = mo.ui.text(label="Sample / device")
    ready = mo.ui.checkbox(label="The sample is mounted and the PPMS chamber is ready for a cooldown")
    start = mo.ui.run_button(label="Start cooldown", kind="success")
    abort = mo.ui.run_button(label="Abort", kind="danger")
    mo.vstack([
        mo.md("## Cooldown\nRamps the PPMS down at a fixed rate and plots G = X(numerator) / X(denominator) "
              "against temperature."),
        mo.hstack([numerator, denominator], justify="start"),
        mo.hstack([target, rate], justify="start"),
        mo.hstack([amplitude, frequency], justify="start"),
        mo.hstack([name, sample], justify="start"),
        ready,
        mo.hstack([start, abort], justify="start"),
    ])
    return abort, amplitude, denominator, frequency, name, numerator, rate, ready, sample, start, target


@app.cell
def _(amplitude, denominator, frequency, mo, name, numerator, rate, ready, runs, sample, start, target):
    mo.stop(not start.value)
    mo.stop(not name.value.strip(), mo.callout(mo.md("Enter your name first."), kind="warn"))
    mo.stop(not ready.value, mo.callout(mo.md("Confirm the sample and the chamber are ready."), kind="warn"))
    runs.user = name.value.strip()
    try:
        _rec = runs.submit(
            "from flex_exp.cooldown import cooldown as run", name="cooldown",
            params={"numerator": numerator.value, "denominator": denominator.value, "target": target.value,
                    "rate": rate.value, "amplitude": amplitude.value, "frequency": frequency.value,
                    "user": runs.user, "sample": sample.value.strip()})
    except Exception as _e:
        _who = ""
        try:
            _latest = runs.runs(1)[0]
            if _latest["status"] == "running":
                _who = f" (started by {_latest['origin'].get('user') or 'someone'})"
        except Exception:
            pass
        _out = mo.callout(mo.md(f"**Not started{_who}:** {_e}"), kind="danger")
    else:
        _out = mo.callout(mo.md(f"Started `{_rec['id']}`"), kind="success")
    _out
    return


@app.cell
def _(abort, mo, runs):
    mo.stop(not abort.value)
    try:
        runs.abort()
        _out = mo.callout(mo.md("Abort requested. Stopping a run does **not** stop the PPMS ramp."), kind="warn")
    except Exception as _e:
        _out = mo.callout(mo.md(f"**Could not abort:** {_e}"), kind="danger")
    _out
    return


@app.cell
def _():
    follow = {"run": None, "since": 0, "rows": [], "tail": []}
    return (follow,)


@app.cell
def _(mo):
    refresh = mo.ui.refresh(options=["2s", "5s"], default_interval="2s", label="Live")
    refresh
    return (refresh,)


@app.cell
def _(fm, follow, html, mo, refresh, runs):
    refresh
    _recent = [r for r in runs.runs(10) if r["name"] == "cooldown"]
    mo.stop(not _recent, mo.md("_No cooldown has run on this station yet._"))
    _rec = _recent[0]
    if _rec["id"] != follow["run"]:
        follow.update(run=_rec["id"], since=0, rows=[], tail=[])
    _new = runs.run(_rec["id"], follow["since"])
    follow["since"] = _new["lines"]
    follow["rows"] += fm.data_rows(_new["log"])
    follow["tail"] = (follow["tail"] + [_l for _l in _new["log"] if not _l.startswith("DATA ")])[-10:]

    _p = _rec["params"]
    _who = " · ".join(filter(None, (_rec["origin"].get("user"), _p.get("sample"))))
    _head = (f"**{_rec['status']}** · {_who or 'unknown'} · to {_p.get('target')} K at {_p.get('rate')} K/min "
             f"· `{_rec['id']}`")
    _kinds = {"running": "info", "done": "success", "failed": "danger", "aborted": "warn", "interrupted": "warn"}
    _parts = [mo.callout(mo.md(_head), kind=_kinds.get(_rec["status"], "neutral"))]
    if _rec["status"] in ("aborted", "failed", "interrupted"):
        _parts.append(mo.callout(mo.md(
            f"**The PPMS may still be ramping to {_p.get('target')} K at {_p.get('rate')} K/min.** "
            "Stopping the run does not stop it: check and stop it from the PPMS PC."), kind="danger"))
    _rows = follow["rows"]
    if _rows:
        import altair as alt

        _step = max(1, len(_rows) // 2000)
        _points = [r for r in _rows[::_step] if r["G"] is not None]
        _last = _rows[-1]
        _parts.append(mo.md(f"T = **{_last['T']:.3f} K** · G = **{_last['G'] if _last['G'] is None else format(_last['G'], '.5g')}**"
                            f" · {_last['t'] / 60:.1f} min · {len(_rows)} points"))
        if _points:
            _parts.append(alt.Chart(alt.Data(values=_points)).mark_line().encode(
                x=alt.X("T:Q", title="T (K)", scale=alt.Scale(zero=False)),
                y=alt.Y("G:Q", title="G = X(numerator) / X(denominator)", scale=alt.Scale(zero=False)),
            ).properties(height=320, width="container"))
    _parts.append(mo.accordion({"Log": mo.Html(
        "<pre style='font-size:12px'>" + html.escape("\n".join(follow["tail"])) + "</pre>")}))
    mo.vstack(_parts)
    return


if __name__ == "__main__":
    app.run()
