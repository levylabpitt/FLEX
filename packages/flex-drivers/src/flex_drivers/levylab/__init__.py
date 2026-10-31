"""Drivers for LevyLab Instrument-Framework apps (JSON-RPC over ZMQ)."""

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
}


def lvclass_registry() -> dict[str, str]:
    """{LabVIEW class: "module:Class"} from each driver's ``lv_class``/``lv_class_aliases``,
    for CESession."""
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
