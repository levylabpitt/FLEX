# Dashboard

The dashboard is the CLI's functionality in the browser: a single-page UI
served by a small FastAPI app in `flex-core`. All logic lives in the core
services; the dashboard only exposes them.

```
flex dashboard            # http://127.0.0.1:8756
```

`--host` and `--port` override the defaults. The **Exit** button in the
header stops the server (you can also Ctrl-C the terminal).

## Tabs

- **Ecosystem** (home) — the discovered ecosystem manifests with the active
  one marked; an **Activate** button per manifest, or activate any manifest
  by path. "Advanced: raw configuration" edits the active config TOML
  directly, validated against the config schema before saving.
- **Integrations** — the official package list with install/uninstall
  buttons.
- **Drivers** — every known driver, searchable; enable/disable each, and
  **Probe** an enabled driver (connect and query its identity).
- **Experiments** — recent experiment records; click one for its
  measurements, data-file pointers, and notes.

## Security

The dashboard is a localhost tool. It binds to `127.0.0.1` by default, and
every request's `Host` header is checked: anything other than
`localhost`/`127.0.0.1`/`[::1]` is rejected with 403, which blocks DNS
rebinding and cross-site requests against the local server.
