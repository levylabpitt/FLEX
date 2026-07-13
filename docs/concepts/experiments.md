# Experiments & data

Three objects, three scopes:

- **Experiment** — a session: instruments, services, one log file, one
  metadata record.
- **Measurement** — one data file plus one metadata record, always used as a
  context manager.
- **Scan** — an autonomous loop that runs *inside* a measurement.

## Experiment

`Experiment` is a context manager. On construction it loads the active
configuration, builds its services from it (metadata store, storage backend,
event bus with configured hooks), records an experiment-start row, and opens
a per-experiment log file. On exit it records the end time, fires
`experiment.end`, releases the services, and closes every registered
instrument.

```python
with Experiment("jane") as exp:
    lockin = exp.add(SR7270, "lockin", "USB0::...")   # construct + register
    exp.lockin                                        # attribute access by name
```

IDs are sortable and collision-safe: `YYYYMMDDHHMMSS-<4 hex chars>`.

Inside Jupyter, every executed cell is recorded as a note with
`kind="cell"` (disable with `cell_log=False`), so the code that produced a
dataset is always recoverable.

Instruments can also come from configuration: `exp.load_station("cryo1")`
instantiates everything in the config's `[stations.cryo1]` block — see
[Ecosystems & stations](ecosystems.md#stations-at-runtime).

In Jupyter or VS Code's Interactive Window, every `Experiment` shows a live
summary card (id, user, instruments) that updates as instruments are added
and again when the experiment ends — since `with Experiment(...) as exp:`
never makes `exp` the last expression of a cell, `_repr_html_` alone would
never render it, so `flex.display.auto_display`/`refresh_display` push it
explicitly instead. Routine logging is quieted to WARNING in interactive
sessions for the same reason (see `flex.log.enable_console`) so the card
stays the signal, not log lines. `CESession` (below) is just an `Experiment`
subclass with a richer card — nothing CESession-specific about the mechanism.

## Measurement

`exp.measurement(name)` returns a `Measurement` context manager owning one
data file. Two recording styles, freely mixed: push rows yourself with
`add_row(**values)`, or `register()` parameters/callables and call
`read_point(**setpoints)` to read them all and record the row. Columns are
fixed by the first data point; `add_array()` stores free-form arrays;
`add_note()` attaches a note to this measurement. See the
[Quickstart](../quickstart.md#measurements-without-scans) for an example.

On entry, the writer (from `[data] writer`, overridable per measurement)
opens the file with embedded metadata — experiment/measurement IDs, name,
user, start time, and a full instrument snapshot — and a measurement-start
row is recorded.

On exit — normal or not — in this order:

1. the writer is closed (a failure is logged; the file may be incomplete),
2. the storage backend finalizes the file (remote backends upload here; a
   failure is logged and the record falls back to the local path),
3. the metadata record is updated with end time, file pointer, and an
   `aborted` flag if the block was left through an exception,
4. `measurement.end` (or `measurement.abort`) fires.

Writers always write to a local path; remote storage acts only in step 2, so
a network failure can never corrupt a live measurement.

## Scan and sweep

`sweep(target, values, delay=...)` describes one axis — a `Parameter` or any
one-argument callable, its values, and pacing (plus optional `before`/`after`
per-pass callbacks). `Scan(*axes)` iterates them as a grid (first axis
outermost) and records a row per point:

```python
Scan(sweep(gate, np.linspace(0, 1, 101), delay=0.01)) \
    .measure(lockin.x, lockin.y) \
    .each(update_plot) \
    .on_abort(lambda: gate(0)) \
    .run(exp, name="gate sweep")
```

`run()` wraps everything in a new measurement. On any interruption —
including Ctrl-C — the `on_abort` callbacks run **first** (errors in one are
logged, the rest still run), *then* the measurement context exits: file
finalized, record marked aborted, `measurement.abort` fired, and only then
does the interrupt propagate.

## Where files land

With no configuration, everything goes under the per-user data directory
(`platformdirs`, e.g. `%LOCALAPPDATA%/flex/data` on Windows); set
`[data] root` to move it. Local storage lays files out by year:

```
{root}/{year}/{experiment_id}/experiment.log
{root}/{year}/{experiment_id}/{measurement_id}.h5
```

(`year` is the first four characters of the experiment ID.) Remote backends
like Nextcloud decide their own final location; the metadata record always
holds the canonical `FilePointer`.

## Metadata records

The metadata store (from `[db] backend`; SQLite by default) keeps three
tables: **experiments** (id, user, name, start/end, instruments, config),
**measurements** (id, experiment, name, start/end, file pointer, aborted),
and **notes** (free text, `kind` = `note` | `cell` | `log`). Browse them with
`flex experiments` / `flex measurements <id>` or the
[dashboard](dashboard.md).

Store failures never kill a run: if the store is unavailable or a write
fails, it is logged and the experiment continues. Opt into hard failures with
`[exp] strict_metadata = true`.

## Comms

`[comms] backend` (`"none"` by default) notifies an external system of the
experiment lifecycle — currently just `flex-asana`'s `"asana"` (one Asana
task per experiment, stamped with the start time and assigned to the user —
unassigned if the handle can't be resolved, never a hard failure; the end
time fills in when the experiment ends — see its package docstring for the
environment variables it reads). `Experiment` builds the backend and calls it
wrapped in try/except, same as the metadata store: a missing token,
unreachable API, or misconfigured project never breaks a run, only logs a
warning. Pass `Experiment(..., notify=False)` to skip it for one run without
touching the ecosystem config.

If `flex-asana` is installed and `python -m flex_asana.update_users` has been
run at least once (regenerates a `Literal` of workspace handles from Asana —
rerun it when people join/leave), `Experiment(user=...)` and
`CESession(user=...)` get IDE autocomplete for known handles; otherwise
`user` is (and always accepts) a plain string.

## Hooks and events

Every lifecycle transition is emitted on the experiment's `EventBus`:
`experiment.start`, `experiment.end`, `measurement.start`,
`measurement.end`, `measurement.abort`, `note.added`, `instrument.added`.

Hooks subscribe from configuration — any callable
`fn(event, experiment, **payload)` referenced by a `"module:function"`
string:

```toml
[hooks]
on_experiment_end = ["some_package.hooks:notify"]
```

Keys may use the `on_<event with _>` form shown or the bare event name.
Subscriber exceptions are logged and swallowed: a broken webhook must never
break a running experiment. A hook that fails to *load* is also only a
warning. This is the general-purpose extension point; official integrations
like Asana use the more specific `[comms]` layer instead (above), matching
how `[db]`/`[data]`/`[storage]` work rather than requiring hand-wired hooks.

## CESession

`CESession` (LevyLab-specific, in `flex-exp`) is an `Experiment` subclass
that gets its instruments from the LabVIEW *Configure Experiments* VI file
instead of code or config: it reads `Control Experiment.json`, matches each
entry's LabVIEW class against `lvclass_registry()` (see
[Instruments & drivers](instruments.md#levylab-drivers-and-lv_class)), and
connects a driver per instrument. `exp.update()` re-reads the file and
connects anything added while running.

Its card (inherited from `Experiment`, see above) additionally shows device,
station, and wiring. Pass `verbose=True` to also print a line as each
instrument connects — useful while debugging a new station.

`CESession` and `load_station()` are two independent mechanisms for the same
job — populating `exp.instruments`. One is driven by the lab's LabVIEW
tooling, the other by `[stations.*]` config; everything downstream
(measurements, scans, records, hooks) is identical. Usage examples are in the
[LevyLab guide](../levylab.md).
