# Dashboard

The dashboard is the CLI's functionality in the browser: a single-page UI
served by a small FastAPI app in `flex-core`. All logic lives in the core
services; the dashboard only exposes them.

It is served by the [tray app](architecture.md#the-tray-app), which also
keeps this PC's station running:

```
flex app                 # http://127.0.0.1:8756 (--port to change)
pythonw -m flex app      # the same, without a console window
```

Clicking the tray icon opens the dashboard; "Quit FLEX" in the tray menu
stops it and the station. The header shows the station and runner status,
with **Start** / **Restart** / **Stop** for the station.

## Tabs

- **Station** (home) — live panels for a station server: this PC's own
  `flex serve` by default, or any other PC's: type its address and port
  (`ppms-pc`, `29500`) and press **Connect**; **Show local** switches back.
  Panels are auto-generated from the server's `describe`: settable
  parameters get input fields, gettable ones live readouts, array parameters
  (e.g. a spectrometer's `spectrum`) live plots — all fed by the server's
  event stream over a WebSocket. No per-instrument UI code needed.
- **Runs** — this PC's runner: recent runs with their status, the selected
  run's log, plots of any numeric arrays in its result, and **Abort** while
  it runs.
- **Config** — edits the active flex.toml directly, validated against the
  config schema before saving. Saving restarts an idle station so the edit
  applies; a running experiment is never aborted — you are told to restart
  the station after it ends.
- **Drivers** — every driver available in this environment, searchable;
  **Probe** connects one and queries its identity.
- **Experiments** — recent experiment records; click one for its
  measurements, data-file pointers, instruments, notes, cells and logs.

## Security

The dashboard is a localhost tool. It binds to `127.0.0.1`, and every
request's `Host` header is checked: anything other than
`localhost`/`127.0.0.1`/`[::1]` is rejected with 403, which blocks DNS
rebinding and cross-site requests against the local server.
