"""FLEX demo: the "levylab" ecosystem — real lab config, both driver families.

Run it from the repo root:

    uv run python tests/test_levylab_ecosystem.py

What this exercises:

  1. Loads the *real* bundled `levylab` manifest (ecosystems/levylab.toml) --
     proves ecosystem resolution/loading genuinely works, not a stand-in.
  2. A LevyLab driver (levylab.lockin) via the manual [stations.*] path:
     Experiment.load_station().
  3. A normal, non-LevyLab driver (colby.pdl, a VISA instrument) via the
     same manual [stations.*] path -- same mechanism, any driver works.
  4. A LevyLab driver via CESession -- the fully automatic path.
  5. Why there's no "normal driver via CESession": CESession only
     auto-discovers drivers that declare an `lv_class` (a LabVIEW class
     name) -- that's a LevyLab-specific concept. A general VISA/TCP/Serial
     driver has no LabVIEW counterpart, so CESession has nothing to match it
     against. This isn't a missing feature, it's a mismatched combination --
     explained inline rather than faked.

Config note -- what's overridden and why:
  The real levylab.toml points [db] at postgres (db.levylab.org) and
  [storage] at Nextcloud (nextcloud.levylab.org) -- real lab infrastructure
  this dev machine can't reach. Everything else (packages, data.writer =
  "tdms", exp.handler = "ce", the driver ecosystem) is exactly what
  `flex ecosystem use levylab` would actually set. So this script loads the
  real manifest, then overrides *only* db/storage to local equivalents
  (sqlite + local) purely so the demo can run end-to-end without lab network
  access, and adds a `[stations.demo]` block (the real manifest ships with
  none — see the comment in ecosystems/levylab.toml explaining why stations
  are per-machine, not lab-wide). On an actual lab machine with real
  credentials, you'd skip both overrides.

Where things land (after the local override): same layout as
test_default_ecosystem.py -- SQLite metadata + local files under
flex.ecosystem.default_data_root() -- except measurement data is TDMS
(.tdms), the real levylab.toml's [data] writer choice, not HDF5.

Nothing here touches your real active ecosystem
(%LOCALAPPDATA%/flex/config.toml).
"""

from __future__ import annotations

import tomllib

from flex.ecosystem import FlexConfig, default_data_root
from flex.pkgmanager import ecosystems
from flex_exp import CESession, Experiment


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# -----------------------------------------------------------------------------
section("Loading the real 'levylab' ecosystem manifest")
# -----------------------------------------------------------------------------
manifest = ecosystems.resolve("levylab")
print(f"Manifest file:  {manifest}")

raw = tomllib.loads(manifest.read_text(encoding="utf-8"))
print(
    f"Real config -- db.backend={raw['db']['backend']}  "
    f"storage.backend={raw['storage']['backend']}  "
    f"data.writer={raw['data']['writer']}  exp.handler={raw['exp']['handler']}"
)

# Override db/storage to local (see module docstring); add two demo stations
# -- kept separate so each load_station() call below isolates one driver's
# failure instead of the first one aborting the whole station load.
raw["db"] = {"backend": "sqlite"}
raw["storage"] = {"backend": "local"}
raw["stations"] = {
    "demo_lockin": {"instruments": {"lockin": {"driver": "levylab.lockin", "address": "tcp://localhost:29170"}}},
    "demo_pdl": {"instruments": {"pdl": {"driver": "colby.pdl", "address": "GPIB0::15::INSTR"}}},
}
config = FlexConfig.model_validate(raw)
print(f"Demo config   -- db.backend={config.db.backend}  storage.backend={config.storage.backend}"
      f"  (overridden for this demo; data.writer/exp.handler unchanged)")
print(f"Data root on this machine: {default_data_root()}")
print(
    "Note: [comms] is untouched (backend = \"asana\"), so every Experiment below\n"
    "tries to build flex_asana's AsanaComms. This machine has no\n"
    "ASANA_ACCESS_TOKEN -- you'll see a WARNING, not a crash: Experiment builds\n"
    "the comms backend wrapped in try/except, so a missing/misconfigured\n"
    "integration never breaks an experiment."
)


# -----------------------------------------------------------------------------
section("2. LevyLab driver (levylab.lockin) via Experiment.load_station()")
# -----------------------------------------------------------------------------
with Experiment("demo-user", name="levylab-driver-demo", config=config, cell_log=False) as exp:
    try:
        exp.load_station("demo_lockin")
    except Exception as e:
        # resolve_driver("levylab.lockin") succeeds (the class is found via
        # flex_drivers.levylab.CATALOG); the failure is the connection
        # attempt itself -- no real LevyLab IF app listening here.
        print(f"load_station() failed — expected without real hardware: {e}")
    print(f"Instruments connected: {list(exp.instruments)}")


# -----------------------------------------------------------------------------
section("3. Normal driver (colby.pdl, VISA) via Experiment.load_station()")
# -----------------------------------------------------------------------------
# Same mechanism as above, different driver family entirely -- load_station()
# doesn't care whether a driver is LevyLab-specific or not, it just resolves
# by catalog name and instantiates.
with Experiment("demo-user", name="normal-driver-demo", config=config, cell_log=False) as exp:
    try:
        exp.load_station("demo_pdl")
    except Exception as e:
        print(f"load_station() failed — expected without real hardware/VISA backend: {e}")
    print(f"Instruments connected: {list(exp.instruments)}")


# -----------------------------------------------------------------------------
section("4. LevyLab driver via CESession — fully automatic path")
# -----------------------------------------------------------------------------
try:
    ce = CESession(timeout=2.0)
except FileNotFoundError as e:
    # CESession reads %LOCALAPPDATA%/Levylab/Control Experiment/Control
    # Experiment.json, written by the actual LevyLab "Configure Experiments"
    # VI. Without that VI ever having run and saved on this machine, there's
    # nothing for CESession to read -- this is the expected failure here.
    print(f"CESession could not start — expected without the CE VI having run: {e}")
except Exception as e:
    print(f"CESession failed for another reason: {e}")
else:
    print(f"Connected: {list(ce.instruments)}")
    ce.end()        # record the end time / fire hooks, then release the instruments
    ce.close_all()


# -----------------------------------------------------------------------------
section("5. Why there's no 'normal driver via CESession'")
# -----------------------------------------------------------------------------
from flex_drivers.colby.pdl import ColbyPDL
from flex_drivers.levylab.lockin import Lockin

print(f"Lockin.lv_class   = {Lockin.lv_class!r}   (a real LabVIEW class name)")
print(f"ColbyPDL.lv_class = {getattr(ColbyPDL, 'lv_class', '<no such attribute>')!r}")
print(
    "ColbyPDL has no lv_class at all -- it's a VISA driver with no LabVIEW\n"
    "counterpart, so CESession's lvclass_registry() (derived from every\n"
    "driver's own lv_class) has nothing to match it against. Not a bug --\n"
    "CESession is specifically the LevyLab-IF-VI-driven path; a general\n"
    "driver reaches an Experiment through load_station() (see step 3) or a\n"
    "direct import instead."
)

print("\nDone.")
