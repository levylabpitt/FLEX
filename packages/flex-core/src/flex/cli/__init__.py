"""The ``flex`` command line interface — a thin UI over flex-core services."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Column, Table

app = typer.Typer(help="FLEX: Framework for Laboratory EXperiments", no_args_is_help=True)
ecosystem_app = typer.Typer(help="Activate and inspect ecosystem configurations", no_args_is_help=True)
new_app = typer.Typer(help="Scaffold new drivers and packages", no_args_is_help=True)
app.add_typer(ecosystem_app, name="ecosystem")
app.add_typer(new_app, name="new")

console = Console()


# -- packages & drivers -------------------------------------------------------


@app.command("list")
def list_(drivers: bool = typer.Option(False, "--drivers", help="List drivers instead of packages")):
    """List official FLEX packages (or drivers) and their status."""
    from flex.pkgmanager import PackageManager

    manager = PackageManager()
    if drivers:
        table = Table("Driver", "Package", "Available", "Enabled")
        for d in manager.list_drivers():
            table.add_row(
                d.name,
                d.package,
                "[green]yes[/]" if d.available else "[dim]no[/]",
                "[green]yes[/]" if d.enabled else "[dim]no[/]",
            )
        console.print(table if table.rows else "No drivers known. Install a driver package first.")
        return
    table = Table("Package", "Group", "Installed", "Summary")
    for p in sorted(manager.list_packages(), key=lambda p: (p.group, p.name)):
        installed = f"[green]{p.installed}[/]" if p.installed else "[dim]-[/]"
        table.add_row(p.name, p.group, installed, p.summary)
    console.print(table)


@app.command()
def install(packages: list[str]):
    """Install official FLEX packages into this environment."""
    from flex.pkgmanager import PackageManager

    PackageManager().install(*packages)
    console.print(f"[green]Installed:[/] {', '.join(packages)}")


@app.command()
def remove(packages: list[str]):
    """Remove FLEX packages from this environment."""
    from flex.pkgmanager import PackageManager

    PackageManager().remove(*packages)
    console.print(f"[green]Removed:[/] {', '.join(packages)}")


@app.command()
def enable(driver: str):
    """Enable a driver (installs its package if needed)."""
    from flex.pkgmanager import PackageManager

    info = PackageManager().enable_driver(driver)
    console.print(f"[green]Enabled:[/] {info.name} (from {info.package})")


@app.command()
def disable(driver: str):
    """Disable a driver in the active configuration."""
    from flex.pkgmanager import PackageManager

    PackageManager().disable_driver(driver)
    console.print(f"[green]Disabled:[/] {driver}")


# -- ecosystem -----------------------------------------------------------


def _resolve_manifest(target: str) -> Path:
    path = Path(target)
    if path.exists():
        return path
    candidate = Path("ecosystems") / f"{target}.toml"
    if candidate.exists():
        return candidate
    raise typer.BadParameter(f"No manifest at '{target}' (also tried {candidate})")


@ecosystem_app.command()
def use(
    manifest: str = typer.Argument(help="Manifest file, or name under ./ecosystems/"),
    install: bool = typer.Option(True, help="Install the packages the ecosystem lists"),
):
    """Activate an ecosystem: install its packages, make it the active config."""
    from flex import ecosystem

    cfg = ecosystem.activate(_resolve_manifest(manifest), install=install)
    console.print(f"[green]Ecosystem '{cfg.ecosystem.name}' active[/] -> {ecosystem.ACTIVE_CONFIG}")


@ecosystem_app.command()
def show():
    """Show the active configuration (resolved)."""
    from flex.ecosystem import find_config, load_config

    source = find_config()
    cfg = load_config()
    console.print(f"[bold]Source:[/] {source or '(built-in defaults)'}")
    table = Table("Setting", "Value")
    table.add_row("ecosystem", cfg.ecosystem.name)
    table.add_row("db.backend", cfg.db.backend)
    table.add_row("data.writer", cfg.data.writer)
    table.add_row("data.root", str(cfg.data.root))
    table.add_row("storage.backend", cfg.storage.backend)
    table.add_row("exp.handler", cfg.exp.handler)
    table.add_row("drivers.enabled", ", ".join(cfg.drivers.enabled) or "-")
    table.add_row("stations", ", ".join(cfg.stations) or "-")
    console.print(table)


@ecosystem_app.command()
def validate(manifest: str = typer.Argument(help="Manifest file, or name under ./ecosystems/")):
    """Validate a manifest: schema, and that its components can be resolved."""
    from flex import components
    from flex.ecosystem import load_config

    path = _resolve_manifest(manifest)
    cfg = load_config(path)
    console.print(f"[green]Schema OK[/] ({path})")
    checks = [("db", cfg.db.backend), ("writer", cfg.data.writer), ("storage", cfg.storage.backend)]
    failures = 0
    for group, name in checks:
        try:
            components.resolve(group, name)
            console.print(f"  [green]ok[/]  {group}: {name}")
        except components.ComponentError as e:
            failures += 1
            console.print(f"  [yellow]--[/]  {group}: {name} — {e}")
    if failures:
        console.print("[yellow]Some components are not installed yet; "
                      "`flex ecosystem use` will install the listed packages.[/]")


# -- browsing ------------------------------------------------------------


@app.command()
def experiments(
    user: str = typer.Option("", help="Filter by user"),
    last: int = typer.Option(20, help="Number of experiments to show"),
):
    """Browse recorded experiments."""
    from flex.ecosystem import load_config

    store = load_config().build_db()
    try:
        table = Table(Column("ID", no_wrap=True), "User", "Name", "Start", "End", "Instruments")
        for e in store.list_experiments(user=user or None, limit=last):
            table.add_row(
                e.id, e.user, e.name or "-",
                str(e.start_time or "-"), str(e.end_time or "[running]"),
                ", ".join(e.instruments) or "-",
            )
        console.print(table)
    finally:
        store.close()


@app.command()
def measurements(experiment_id: str):
    """List the measurements (and data files) of an experiment."""
    from flex.ecosystem import load_config

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
        if notes:
            console.print(f"[dim]{len(notes)} note(s); kinds: "
                          f"{', '.join(sorted({n.kind for n in notes}))}[/]")
    finally:
        store.close()


@app.command()
def instruments(probe: bool = typer.Option(False, "--probe", help="Connect and query *IDN*")):
    """List instruments configured in the active station(s)."""
    from flex.ecosystem import load_config
    from flex.pkgmanager import PackageManager

    cfg = load_config()
    if not cfg.stations:
        console.print("No stations defined in the active configuration.")
        raise typer.Exit()
    manager = PackageManager()
    table = Table("Station", "Instrument", "Driver", "Address", *(["IDN"] if probe else []))
    for station, spec in cfg.stations.items():
        for name, inst in spec.instruments.items():
            row = [station, name, inst.driver, inst.address or "-"]
            if probe:
                try:
                    cls = manager.resolve_driver(inst.driver)
                    args = (inst.address,) if inst.address else ()
                    with cls(name, *args, **inst.options()) as device:
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
    """Generate a FLEX package skeleton (installable, with a driver catalog)."""
    from flex.cli.scaffold import create_package

    root = create_package(name, out)
    console.print(f"[green]Created[/] {root} (install with: pip install -e {root})")


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8756),
):
    """Launch the FLEX dashboard (requires flex-dashboard)."""
    try:
        from flex_dashboard import run
    except ImportError as e:
        console.print("[red]flex-dashboard is not installed.[/] Run: flex install flex-dashboard")
        raise typer.Exit(1) from e
    run(host=host, port=port)


@app.command()
def version():
    """Show versions of every installed FLEX package."""
    from flex.pkgmanager import PackageManager

    table = Table("Package", "Version")
    for p in PackageManager().list_packages():
        if p.installed:
            table.add_row(p.name, p.installed)
    console.print(table)


if __name__ == "__main__":
    app()
