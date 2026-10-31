# CLI reference

Every command of the `flex` command-line tool. Global behavior: running
`flex` with no arguments prints help. `python -m flex` runs the same CLI.

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
| `flex measurements <experiment-id>` | List an experiment's measurements (times, aborted flag, data file) and its note, cell and log counts. |
| `flex instruments` | List the instruments configured in the active `[instruments.*]` blocks. `--probe` connects each one and shows its identity (or the error). |

## Scaffolding

| Command | Does |
|---|---|
| `flex new driver <Name>` | Write a driver skeleton `<name>.py` in the current directory. `--protocol visa\|tcp\|serial\|zmq` picks the base class (default `visa`); `--out <dir>` changes the destination. Refuses to overwrite. |
| `flex new package <name>` | Create an installable driver-package skeleton (`pyproject.toml`, `src/<module>/__init__.py`, `tests/`). `--out <dir>` changes the destination. Its drivers are named in flex.toml as `driver = "<module>.<file>:<Class>"`. |

See [Write a driver](../tutorials/write-a-driver.md) for both in context.

## Station and runs

| Command | Does |
|---|---|
| `flex serve` | Host this PC's `[instruments.*]` as a station server: JSON-RPC commands on `[server] port` (default 29500), event stream on port+1, background logging of `log = [...]` parameters to the DB. Also runs the script runner (`[runner] port`, default 29510) unless `[runner] enabled = false`. `--config <path>` picks the config; `--quiet` suppresses console output (the log is `<data root>/serve.log`). Connect with `flex.connect("tcp://<host>:29500")`. |
| `flex monitor [parameter]` | Browse background-logged values (newest first, `--last <n>`). `--follow` streams live events from a running server instead (`--address` for a remote one). |
| `flex run <script.py>` | Submit a script defining `run(station, **params)` to the runner and print its log until it ends. `-p key=value` passes a parameter (JSON if it parses); `--entry` names another function; `--detach` returns right after submitting; `--address` targets another runner. Ctrl-C detaches; the run continues. |
| `flex runs` | List recent runs (`--last <n>`, default 10; `--address`). |
| `flex abort [run-id]` | Stop the running script; its `finally` blocks run. `--address` targets another runner. |

## App & version

| Command | Does |
|---|---|
| `flex app` | The tray app: starts `flex serve` in the background and serves the [dashboard](../concepts/dashboard.md) on `http://127.0.0.1:8756` (`--port` changes it). If it is already running, opens the dashboard. Needs `flex-core[app]`; `pythonw -m flex app` runs it without a console. |
| `flex version` | Show the version of every installed FLEX package. |
