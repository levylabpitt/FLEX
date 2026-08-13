# CLI reference

Every command of the `flex` command-line tool. Global behavior: running
`flex` with no arguments prints help.

## Drivers

| Command | Does |
|---|---|
| `flex drivers` | List every driver available in this environment and the class it resolves to. |

## Configuration

| Command | Does |
|---|---|
| `flex config show` | Print the resolved active configuration and its source file. |
| `flex config validate <path>` | Check a config file: schema, then whether its db/writer/storage/comms components and instrument drivers resolve in this environment. |

## Records

| Command | Does |
|---|---|
| `flex experiments` | Browse recorded experiments. `--user <name>` filters; `--last <n>` limits (default 20). |
| `flex measurements <experiment-id>` | List an experiment's measurements (times, aborted flag, data file) and note count. |
| `flex instruments` | List the instruments configured in the active `[instruments.*]` blocks. `--probe` connects each one and shows its identity (or the error). |

## Scaffolding

| Command | Does |
|---|---|
| `flex new driver <Name>` | Write a driver skeleton `<name>.py` in the current directory. `--protocol visa\|tcp\|serial\|zmq` picks the base class (default `visa`); `--out <dir>` changes the destination. Refuses to overwrite. |
| `flex new package <name>` | Create an installable driver-package skeleton (`pyproject.toml`, `src/<module>/__init__.py` with a `CATALOG` dict, `tests/`). `--out <dir>` changes the destination. |

See [Write a driver](../tutorials/write-a-driver.md) for both in context.

## Server

| Command | Does |
|---|---|
| `flex serve` | Host this PC's `[instruments.*]` as a station server: JSON-RPC commands on `[server] port` (default 29500), event stream on port+1. `--config` and `--port` override. Connect with `flex.connect("tcp://<host>:29500")`. |

## Dashboard & version

| Command | Does |
|---|---|
| `python -m flex dashboard` | Launch the [web dashboard](../concepts/dashboard.md). `--host` (default `127.0.0.1`), `--port` (default `8756`). Use the module form, not `flex dashboard` — see the dashboard page for why. |
| `flex version` | Show the version of every installed FLEX package. |
