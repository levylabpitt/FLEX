# Dashboard

The dashboard is the CLI's functionality in the browser: a single-page UI
served by a small FastAPI app in `flex-core`. All logic lives in the core
services; the dashboard only exposes them.

```
python -m flex dashboard            # http://127.0.0.1:8756
```

`--host` and `--port` override the defaults. The **Exit** button in the
header stops the server (you can also Ctrl-C the terminal).

!!! note
    Use `python -m flex dashboard`, not the bare `flex dashboard` console
    script. On Windows, `flex.exe` stays open for the life of the server and
    holds a file lock on itself, which blocks pip/uv from touching the
    environment while it runs. `python -m flex` runs the same CLI without
    that lock.

## Tabs

- **Station** (home) — live panels for every station server in
  `[ui] stations` (default: this PC's own `flex serve`). Panels are
  auto-generated from each server's `describe`: settable parameters get
  input fields, gettable ones live readouts, array parameters (e.g. a
  spectrometer's `spectrum`) live plots — all fed by the server's event
  stream over a WebSocket. No per-instrument UI code needed.
- **Config** — edits the active flex.toml directly, validated
  against the config schema before saving.
- **Drivers** — every driver available in this environment, searchable;
  **Probe** connects one and queries its identity.
- **Experiments** — recent experiment records; click one for its
  measurements, data-file pointers, and notes.

The dashboard itself can run on any PC: point `[ui] stations` at remote
station servers (`["tcp://ppms-pc:29500", "tcp://bench2:29500"]`) and one
browser page shows the whole physical station, even when its instruments
are split across machines.

## Security

The dashboard is a localhost tool. It binds to `127.0.0.1` by default, and
every request's `Host` header is checked: anything other than
`localhost`/`127.0.0.1`/`[::1]` is rejected with 403, which blocks DNS
rebinding and cross-site requests against the local server.
