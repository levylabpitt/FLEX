# CLI reference

Every command of the `flex` command-line tool. Global behavior: running
`flex` with no arguments prints help.

## Packages & drivers

| Command | Does |
|---|---|
| `flex list` | List official packages: group, installed version, summary. |
| `flex list --drivers` | List drivers instead: parent package, available (package installed), enabled. |
| `flex install <pkg>...` | Install official packages (editable from a repo checkout, else from GitHub — see [Architecture](../concepts/architecture.md#installation)). |
| `flex remove <pkg>...` | Uninstall packages. |
| `flex enable <driver>` | Add a driver to `[drivers] enabled` in the active config; installs its parent package first if missing. |
| `flex disable <driver>` | Remove a driver from `[drivers] enabled`. |

## Ecosystems

| Command | Does |
|---|---|
| `flex ecosystem use <manifest>` | Activate an ecosystem: install its packages, make it the active config. `<manifest>` is a file path or a known name (bundled `default`, or the repo's `ecosystems/` folder). `--no-install` skips package installation. |
| `flex ecosystem show` | Print the resolved active configuration and its source file. |
| `flex ecosystem validate <manifest>` | Check a manifest: schema, then whether its db/writer/storage components resolve to installed packages. |

## Records

| Command | Does |
|---|---|
| `flex experiments` | Browse recorded experiments. `--user <name>` filters; `--last <n>` limits (default 20). |
| `flex measurements <experiment-id>` | List an experiment's measurements (times, aborted flag, data file) and note count. |
| `flex instruments` | List instruments configured in the active `[stations.*]` blocks. `--probe` connects each one and shows its identity (or the error). |

## Scaffolding

| Command | Does |
|---|---|
| `flex new driver <Name>` | Write a driver skeleton `<name>.py` in the current directory. `--protocol visa\|tcp\|serial\|zmq` picks the base class (default `visa`); `--out <dir>` changes the destination. Refuses to overwrite. |
| `flex new package <name>` | Create an installable driver-package skeleton (`pyproject.toml`, `src/<module>/__init__.py` with a `CATALOG` dict, `tests/`). `--out <dir>` changes the destination. |

See [Write a driver](../tutorials/write-a-driver.md) for both in context.

## Dashboard & version

| Command | Does |
|---|---|
| `python -m flex dashboard` | Launch the [web dashboard](../concepts/dashboard.md). `--host` (default `127.0.0.1`), `--port` (default `8756`). Use the module form, not `flex dashboard` — see the dashboard page for why. |
| `flex version` | Show the version of every installed FLEX package. |
