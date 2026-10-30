"""The ``flex`` command line interface — a thin UI over flex-core services."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Column, Table

app = typer.Typer(help="FLEX: Framework for Laboratory EXperiments", no_args_is_help=True)
config_app = typer.Typer(help="Inspect and validate the active configuration", no_args_is_help=True)
new_app = typer.Typer(help="Scaffold new drivers and packages", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(new_app, name="new")

console = Console()


# -- drivers ------------------------------------------------------------------


@app.command()
def drivers():
    """List every driver available in this environment."""
    from flex import components

    refs = components.available("drivers")
    if not refs:
        console.print("No drivers found. Install a driver package (e.g. flex-drivers) first.")
        return
    table = Table("Driver", "Class")
    for name in sorted(refs):
        table.add_row(name, refs[name])
    console.print(table)


# -- config -------------------------------------------------------------------


@config_app.command()
def show():
    """Show the active configuration (resolved)."""
    from flex.config import find_config, load_config

    source = find_config()
    cfg = load_config()
    console.print(f"[bold]Source:[/] {source or '(built-in defaults)'}")
    table = Table("Setting", "Value")
    table.add_row("lab.name", cfg.lab.name or "-")
    table.add_row("lab.station", cfg.lab.station or "-")
    table.add_row("db.backend", cfg.db.backend)
    table.add_row("data.writer", cfg.data.writer)
    table.add_row("data.root", str(cfg.data.root))
    table.add_row("storage.backend", cfg.storage.backend)
    table.add_row("exp.handler", cfg.exp.handler)
    table.add_row("instruments", ", ".join(cfg.instruments) or "-")
    console.print(table)


@config_app.command()
def validate(path: str = typer.Argument(help="Configuration file (flex.toml)")):
    """Validate a configuration file: schema, and that its components resolve."""
    from flex import components
    from flex.config import load_config

    cfg = load_config(Path(path))
    console.print(f"[green]Schema OK[/] ({path})")
    checks = [("db", cfg.db.backend), ("writer", cfg.data.writer), ("storage", cfg.storage.backend)]
    if cfg.comms.backend != "none":
        checks.append(("comms", cfg.comms.backend))
    checks += [
        ("drivers", inst.driver) for inst in cfg.instruments.values() if not inst.simulate
    ]
    failures = 0
    for group, name in checks:
        try:
            components.resolve(group, name)
            console.print(f"  [green]ok[/]  {group}: {name}")
        except components.ComponentError as e:
            failures += 1
            console.print(f"  [red]!![/]  {group}: {name} — {e}")
    if failures:
        raise typer.Exit(1)


# -- browsing ------------------------------------------------------------


@app.command()
def experiments(
    user: str = typer.Option("", help="Filter by user"),
    last: int = typer.Option(20, help="Number of experiments to show"),
):
    """Browse recorded experiments."""
    from flex.config import load_config

    store = load_config().build_db()
    try:
        table = Table(Column("ID", no_wrap=True), "User", "Host", "Name", "Start", "End", "Instruments")
        for e in store.list_experiments(user=user or None, limit=last):
            names = [i.name for i in store.list_instruments(e.id)]
            table.add_row(
                e.id, e.user, e.host or "-", e.name or "-",
                str(e.start_time or "-"), str(e.end_time or "[running]"),
                ", ".join(names) or "-",
            )
        console.print(table)
    finally:
        store.close()


@app.command()
def measurements(experiment_id: str):
    """List the measurements (and data files) of an experiment."""
    from flex.config import load_config

    store = load_config().build_db()
    try:
        table = Table(Column("ID", no_wrap=True), "Name", "Start", "End", "Aborted", "File")
        for m in store.list_measurements(experiment_id):
            table.add_row(
                m.id, m.name or "-", str(m.start_time or "-"), str(m.end_time or "-"),
                "[red]yes[/]" if m.aborted else "no", m.file.uri if m.file else "-",
            )
        console.print(table)
        notes = store.list_notes(experiment_id)
        cells = store.list_cells(experiment_id)
        logs = store.list_logs(experiment_id)
        summary = ", ".join(
            f"{len(items)} {label}"
            for items, label in [(notes, "note(s)"), (cells, "cell(s)"), (logs, "log(s)")]
            if items
        )
        if summary:
            console.print(f"[dim]{summary}[/]")
    finally:
        store.close()


@app.command()
def instruments(probe: bool = typer.Option(False, "--probe", help="Connect and query *IDN*")):
    """List instruments configured on this PC ([instruments.*])."""
    from flex.config import load_config

    cfg = load_config()
    if not cfg.instruments:
        console.print("No instruments defined in the active configuration.")
        raise typer.Exit()
    table = Table("Instrument", "Driver", "Address", *(["IDN"] if probe else []))
    for name, inst in cfg.instruments.items():
        driver = "[dim]simulated[/]" if inst.simulate else inst.driver
        row = [name, driver, inst.address or "-"]
        if probe:
            try:
                with inst.build(name) as device:
                    idn = device.idn()
                row.append(f"[green]{idn.get('model') or 'ok'}[/]")
            except Exception as e:
                row.append(f"[red]{e}[/]")
        table.add_row(*row)
    console.print(table)


# -- scaffolding / apps / version -------------------------------------------


@new_app.command("driver")
def new_driver(
    name: str = typer.Argument(help="Class name, e.g. Keithley2400"),
    protocol: str = typer.Option("visa", help="visa | tcp | serial | zmq"),
    out: Path = typer.Option(Path("."), help="Output directory"),
):
    """Generate a driver skeleton."""
    from flex.cli.scaffold import driver_template

    path = out / f"{name.lower()}.py"
    if path.exists():
        raise typer.BadParameter(f"{path} already exists")
    path.write_text(driver_template(name, protocol), encoding="utf-8")
    console.print(f"[green]Created[/] {path}")


@new_app.command("package")
def new_package(
    name: str = typer.Argument(help="Package name, e.g. flex-drivers-mylab"),
    out: Path = typer.Option(Path("."), help="Output directory"),
):
    """Generate a FLEX package skeleton (installable, with a driver registry)."""
    from flex.cli.scaffold import create_package

    if (out / name).exists():
        raise typer.BadParameter(f"{out / name} already exists")
    root = create_package(name, out)
    console.print(f"[green]Created[/] {root} (install with: pip install -e {root})")


@app.command()
def serve(
    config: str = typer.Option(None, help="Config file (default: the active flex.toml)"),
    port: int = typer.Option(None, help="Command port (events on port+1); default [server] port"),
):
    """Host this PC's instruments as a station server, and run experiment scripts for it."""
    from flex.config import load_config
    from flex.runner import RunServer
    from flex.server import StationServer
    from flex.station import Station

    cfg = load_config(config)
    station = Station.load(cfg)
    server = StationServer(station, port=port if port is not None else cfg.server.port)
    runner = None
    if cfg.runner.enabled:
        runner = RunServer(
            cfg.runner.servers or [f"tcp://localhost:{server.port}"], root=Path(cfg.data.root) / "runs",
            port=cfg.runner.port, call_timeout=cfg.runner.call_timeout, token=cfg.runner.token,
        )
    table = Table("Instrument", "Class", "Address", "Logged")
    for name, inst in station.instruments.items():
        params, interval = server.monitor.get(name, ([], 0))
        logged = f"{', '.join(params)} [dim]@{interval:g}s[/]" if params else "-"
        table.add_row(name, type(inst).__name__, inst.address or "-", logged)
    for name, error in station.failed.items():
        table.add_row(name, f"[red]failed: {error}[/]", "-", "-")
    console.print(table)
    console.print(f"[green]Serving station '{station.name}'[/] on port {server.port} "
                  f"(events on {server.pub_port}). Ctrl-C to stop.")
    if runner:
        scope = "the whole LAN, token required" if runner.token else "this PC only"
        console.print(f"[green]Running scripts[/] on port {runner.port} ({scope}); "
                      "stopping aborts a running script.")
    server.start()
    if runner:
        runner.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if runner:
            runner.stop()  # first: an aborted script's cleanup still needs the station
        server.stop()
        station.close()


@app.command()
def monitor(
    parameter: str = typer.Argument(None, help='Full parameter name, e.g. "spectrometer.spectrum"'),
    last: int = typer.Option(20, help="Number of rows to show"),
    follow: bool = typer.Option(False, "--follow", help="Stream live events from a running server"),
    address: str = typer.Option("", help="Server address for --follow (default: the local server)"),
):
    """Browse background-logged parameter values, or stream them live."""
    from flex.config import load_config

    cfg = load_config()
    if follow:
        from flex.client import connect

        target = address or f"tcp://localhost:{cfg.server.port}"
        station = connect(target, timeout=3.0)

        def show(event: dict) -> None:
            if parameter and event.get("parameter") != parameter:
                return
            when = datetime.fromtimestamp(event["ts"]).strftime("%H:%M:%S")
            value, unit = _short(event.get("value")), event.get("unit", "")
            console.print(f"[dim]{when}[/] {event['parameter']} = {value} {unit}".rstrip())

        station.subscribe(show)
        console.print(f"[green]Following {target}[/] (Ctrl-C to stop)")
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            station.close()
        return

    store = cfg.build_db()
    try:
        rows = store.list_monitor(parameter or None, limit=last)
        if not rows:
            console.print("Nothing logged yet. Add `log = [...]` to an [instruments.*] "
                          "entry and run `flex serve`.")
            return
        table = Table("Time", "Station", "Parameter", "Value", "Unit")
        for r in rows:
            table.add_row(str(r.time or "-"), r.station or "-", r.parameter, _short(r.value), r.unit)
        console.print(table)
    finally:
        store.close()


def _runner_client(address: str):
    from flex.config import load_config
    from flex.runner import RunClient

    cfg = load_config()
    return RunClient(address or f"tcp://localhost:{cfg.runner.port}", timeout=3.0, token=cfg.runner.token)


@app.command()
def run(
    script: Path = typer.Argument(..., exists=True, dir_okay=False, help="Python file defining run(station, **params)"),
    param: list[str] = typer.Option([], "--param", "-p", help="Parameter as key=value (value is JSON if it parses)"),
    entry: str = typer.Option("run", help="Function to call"),
    follow: bool = typer.Option(True, "--follow/--detach", help="Print the log until the run ends"),
    address: str = typer.Option("", help="Runner address (default: the local runner)"),
):
    """Submit a script to the runner."""
    import json

    params = {}
    for item in param:
        key, _, raw = item.partition("=")
        try:
            params[key] = json.loads(raw)
        except ValueError:
            params[key] = raw
    client = _runner_client(address)
    try:
        rec = client.submit(script.read_text(encoding="utf-8"), entry=entry, params=params, name=script.stem)
        console.print(f"[green]Started[/] {rec['id']}")
        if not follow:
            return
        try:
            rec = client.wait(rec["id"], on_log=console.print)
        except KeyboardInterrupt:
            console.print(f"Detached; the run continues. `flex abort {rec['id']}` to stop it.")
            return
        color = "green" if rec["status"] == "done" else "red"
        console.print(f"[{color}]{rec['status']}[/]" + (f": {rec['error']}" if rec["error"] else ""))
    finally:
        client.close()


@app.command()
def runs(
    last: int = typer.Option(10, help="Number of runs to show"),
    address: str = typer.Option("", help="Runner address (default: the local runner)"),
):
    """List recent runs."""
    client = _runner_client(address)
    try:
        table = Table("Run", "Name", "Status", "Started", "Took")
        for r in client.runs(last):
            took = f"{(r['finished'] - r['started']):.0f}s" if r["finished"] else "-"
            table.add_row(r["id"], r["name"] or r["entry"], r["status"],
                          datetime.fromtimestamp(r["started"]).strftime("%m-%d %H:%M:%S"), took)
        console.print(table)
    finally:
        client.close()


@app.command()
def abort(
    run_id: str = typer.Argument(None, help="Run id (default: the running one)"),
    address: str = typer.Option("", help="Runner address (default: the local runner)"),
):
    """Stop the running script (its finally-blocks get to run)."""
    client = _runner_client(address)
    try:
        client.abort(run_id)
        console.print("Abort requested.")
    finally:
        client.close()


def _short(value, width: int = 60) -> str:
    text = repr(value)
    return text if len(text) <= width else f"{text[:width]}… ({len(text)} chars)"


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8756),
):
    """Launch the FLEX dashboard."""
    from flex.dashboard import run

    run(host=host, port=port)


@app.command()
def version():
    """Show versions of every installed FLEX package."""
    from importlib import metadata

    known = ["flex", "flex-core", "flex-exp", "flex-drivers", "flex-nextcloud", "flex-asana"]
    table = Table("Package", "Version")
    for name in known:
        try:
            table.add_row(name, metadata.version(name))
        except metadata.PackageNotFoundError:
            pass
    console.print(table)


if __name__ == "__main__":
    app()
