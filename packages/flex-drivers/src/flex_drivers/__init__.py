"""flex_drivers (FLEX v2).

General instrument drivers, organized by vendor. Driver classes are not
imported at package import time; they are looked up lazily through
:data:`CATALOG`, whose values are ``"module:Class"`` references resolvable
with :func:`flex.components.load_ref`.
"""

__version__ = "2.0.0a1"

#: Driver name -> "module:Class" reference.
CATALOG: dict[str, str] = {
    "srs.sr7270": "flex_drivers.srs.sr7270:SR7270",
    "colby.pdl": "flex_drivers.colby.pdl:ColbyPDL",
    "rotrics.dexarm": "flex_drivers.rotrics.dexarm:DexArm",
}
