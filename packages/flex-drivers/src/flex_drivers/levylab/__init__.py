"""FLEX v2 drivers for LevyLab Instrument-Framework apps (JSON-RPC over ZMQ).

Ports of the FLEX v1 ``flex.inst.levylab`` drivers onto
``flex_protocols.ZMQInstrument``. Driver modules are imported lazily via
:data:`CATALOG` — importing this package does not import zmq or any driver
module.
"""

__version__ = "2.0.0a1"

#: Driver name -> "module:Class" reference (resolved with flex.components.load_ref).
CATALOG: dict[str, str] = {
    "levylab.lockin": "flex_drivers.levylab.lockin:Lockin",
    "levylab.krohn_hite": "flex_drivers.levylab.krohn_hite:KrohnHite7008",
    "levylab.transport_server": "flex_drivers.levylab.transport_server:TransportServer",
    "levylab.ppms": "flex_drivers.levylab.ppms:PPMS",
    "levylab.opticool": "flex_drivers.levylab.opticool:Opticool",
    "levylab.cryostation": "flex_drivers.levylab.cryostation:Cryostation",
    "levylab.oxford1820": "flex_drivers.levylab.oxford:Oxford1820",
    "levylab.oxford_vrm": "flex_drivers.levylab.oxford:OxfordVRM",
    "levylab.tc_cf": "flex_drivers.levylab.tc:TC_CF",
    "levylab.tc_mnk": "flex_drivers.levylab.tc:TC_MNK",
    "levylab.aerotech": "flex_drivers.levylab.aerotech:Aerotech",
}


def lvclass_registry() -> dict[str, str]:
    """{LabVIEW class name: "module:Class" reference}, for CESession auto-discovery.

    Derived from each driver's own ``lv_class``/``lv_class_aliases`` class
    attributes (see e.g. flex_drivers.levylab.ppms) -- not a separately
    maintained dict, so it can't drift out of sync with the driver files
    themselves. The five v1 PPMS variants all resolve to the one consolidated
    PPMS driver via its ``lv_class_aliases``. TransportServer has no LabVIEW
    class (``lv_class = None``) and is never included here.
    """
    from flex.components import load_ref

    registry: dict[str, str] = {}
    for ref in CATALOG.values():
        cls = load_ref(ref)
        lv_class = getattr(cls, "lv_class", None)
        if lv_class is None:
            continue
        registry[lv_class] = ref
        for alias in getattr(cls, "lv_class_aliases", ()):
            registry[alias] = ref
    return registry
