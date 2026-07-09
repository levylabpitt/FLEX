# On-Hardware Validation Checklist (v2 acceptance)

Run in the lab, on a station with live Instrument-Framework apps. Tick every
box before switching production work to v2.

## Setup
- [ ] Fresh venv: `pip install -e` the workspace packages (or `uv sync`)
- [ ] `flex ecosystem use ecosystems/levylab.toml` completes; `flex ecosystem show` looks right
- [ ] `NEXTCLOUD_PASSWORD` set; `flex ecosystem validate ecosystems/levylab.toml` all green

## Instruments
- [ ] `flex instruments --probe` reaches every configured IF app
- [ ] `CESession()` boots from the real Configure Experiments VI file;
      the HTML summary shows the correct instruments + wiring
- [ ] A slow/hung IF app produces a `TimeoutError`, and the *next* call
      succeeds (REQ-socket recovery)
- [ ] `exp.update()` picks up an instrument added in the VI while running

## Measurement pipeline
- [ ] A short gate sweep writes a TDMS file **readable by the lab DataViewer**
      (channel layout, units, metadata) — this is the highest-risk item
- [ ] The file uploads to Nextcloud on measurement end; pointer in the DB
- [ ] Experiment + measurement rows appear in PostgreSQL
- [ ] Ctrl-C mid-sweep: file finalized, `aborted` flag set, `on_abort` ramps
      the gate down, instruments still responsive afterwards
- [ ] n8n webhook fires on experiment start/end (check Asana)

## UX
- [ ] `flex dashboard`: packages page installs/enables a driver; experiments
      page shows the runs from today
- [ ] Jupyter: `CESession()` renders the summary card; cells are logged as notes

## Cleanup decisions to confirm with the lab
- [ ] Revoke the Asana token committed in v1 (`src/flex/asana/Asana.py` on main)
- [ ] Plan the v1 `exp`/`meas`/`cell_log` PostgreSQL migration
- [ ] Confirm `flex.lv` (LabVIEW call helpers) can stay retired
- [ ] Decide priority for the deferred .NET/COM drivers (Newport, Ophir, Sphere)
