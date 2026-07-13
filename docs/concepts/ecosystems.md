# Ecosystems & stations

This page explains the concepts; [Build an ecosystem](../build-an-ecosystem.md)
is the how-to, with a complete annotated manifest.

## The hierarchy

Three levels, from lab-wide to per-device:

- An **ecosystem** is a lab's shared setup in one TOML manifest: the packages
  to install plus the service configuration everyone shares — database,
  storage, data format, hooks. One file per lab, versioned in the repo.
- A **station** is one bench's instrument set: a `[stations.<name>]` block
  mapping instrument names to drivers and addresses. Stations are typically
  added *locally* (edited into the active config on that machine), not
  shipped lab-wide — your bench's addresses are not your neighbor's.
- An **instrument entry** names a driver and an address:

```toml
[stations.cryo1.instruments.lockin]
driver = "srs.sr7270"
address = "USB0::0x0A2D::0x001B::12345::RAW"
```

Extra keys in an instrument entry pass straight through to the driver's
constructor as keyword arguments.

## Where manifests live

Manifests are discovered dynamically from two places; nothing is hardcoded:

1. `default.toml`, bundled inside `flex-core` itself
   (`flex.pkgmanager.ecosystems`). It is the explicit form of running with no
   configuration at all: SQLite, HDF5, local files.
2. The repo's top-level `ecosystems/` folder (found when running from a
   workspace checkout). This is where lab manifests like `levylab.toml` live —
   it is repo content, not package content, so a fork can delete, replace,
   or add manifests without touching `flex-core`.

Later locations override earlier ones by name. `flex ecosystem use <name>`
resolves a bare name against these folders; a path to any `.toml` file works
too.

## What activation does — and does not do

`flex ecosystem use <manifest>` does exactly two things:

1. installs the packages listed under `[ecosystem] packages` (see
   [Architecture](architecture.md#installation) for where they come from),
2. copies the manifest to the active-config location, making it the
   configuration every subsequent `Experiment`, CLI command, and dashboard
   session resolves.

It deliberately does **not** configure your bench. `levylab.toml` ships no
`[drivers]` or `[stations.*]` sections: which drivers are enabled and which
instruments live at your bench are per-station concerns. You add those
locally — `flex enable <driver>`, the dashboard's raw-config editor, or
editing the file directly — on top of the activated lab config.

## Configuration resolution

At runtime the active configuration is found by a fixed precedence: explicit
path → `$FLEX_CONFIG` → `./flex.toml` → the activated config in the user data
directory → built-in defaults. The full list, and what each level is for, is
in [Build an ecosystem](../build-an-ecosystem.md#how-the-configuration-is-found).
`./flex.toml` outranking the activated config is the escape hatch: a project
folder can carry its own complete configuration without touching the
machine-wide one.

Every section of the manifest is optional; short component names in it
("postgres", "tdms", "nextcloud") resolve to classes through the package
catalog — see [Architecture](architecture.md#name-resolution).

## Stations at runtime

`exp.load_station("cryo1")` instantiates every instrument in the block —
resolving each `driver` name by catalog, passing the address and extra keys —
and registers them on the experiment. Each `driver` must be enabled first
(`flex enable <driver>`) — see [Instruments &
drivers](instruments.md#driver-packages-and-the-catalog). With `[lab] station` set (or
only one station defined), the name argument is optional. `flex instruments
--probe` test-connects the same entries from the shell.

The LevyLab ecosystem replaces station config with the Configure Experiments
VI: see [CESession](experiments.md#cesession).
