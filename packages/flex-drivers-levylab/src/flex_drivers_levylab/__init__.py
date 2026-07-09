"""FLEX v2 drivers for LevyLab Instrument-Framework apps (JSON-RPC over ZMQ).

Ports of the FLEX v1 ``flex.inst.levylab`` drivers onto
``flex_protocols.ZMQInstrument``. Driver modules are imported lazily via
:data:`CATALOG` / :data:`LVCLASS_REGISTRY` — importing this package does not
import zmq or any driver module.
"""

__version__ = "2.0.0a1"

#: Driver name -> "module:Class" reference (resolved with flex.components.load_ref).
CATALOG: dict[str, str] = {
    "levylab.lockin": "flex_drivers_levylab.lockin:Lockin",
    "levylab.krohn_hite": "flex_drivers_levylab.krohn_hite:KrohnHite7008",
    "levylab.transport_server": "flex_drivers_levylab.transport_server:TransportServer",
    "levylab.ppms": "flex_drivers_levylab.ppms:PPMS",
    "levylab.opticool": "flex_drivers_levylab.opticool:Opticool",
    "levylab.cryostation": "flex_drivers_levylab.cryostation:Cryostation",
    "levylab.oxford1820": "flex_drivers_levylab.oxford:Oxford1820",
    "levylab.oxford_vrm": "flex_drivers_levylab.oxford:OxfordVRM",
    "levylab.tc_cf": "flex_drivers_levylab.tc:TC_CF",
    "levylab.tc_mnk": "flex_drivers_levylab.tc:TC_MNK",
    "levylab.aerotech": "flex_drivers_levylab.aerotech:Aerotech",
}

#: LabVIEW class name (the IF app's lvclass) -> "module:Class" reference.
#: Used by CESession auto-discovery. The five v1 PPMS variants all map to the
#: consolidated PPMS driver (see flex_drivers_levylab.ppms for the history).
#: TransportServer had no LabVIEW class name in v1 and is not listed.
LVCLASS_REGISTRY: dict[str, str] = {
    "Instrument.Lockin.lvclass": "flex_drivers_levylab.lockin:Lockin",
    "Inst.Krohn-Hite-7008.lvclass": "flex_drivers_levylab.krohn_hite:KrohnHite7008",
    "instrument.PPMS.lvclass": "flex_drivers_levylab.ppms:PPMS",
    "instrument.PPMS1.lvclass": "flex_drivers_levylab.ppms:PPMS",
    "instrument.PPMS2.lvclass": "flex_drivers_levylab.ppms:PPMS",
    "instrument.PPMS3.lvclass": "flex_drivers_levylab.ppms:PPMS",
    "instrument.PPMS-W-1.lvclass": "flex_drivers_levylab.ppms:PPMS",
    "instrument.OptiCool.lvclass": "flex_drivers_levylab.opticool:Opticool",
    "instrument.Cryostation.lvclass": "flex_drivers_levylab.cryostation:Cryostation",
    "Instrument.Oxford1820.lvclass": "flex_drivers_levylab.oxford:Oxford1820",
    "Instrument.OxfordVRM.lvclass": "flex_drivers_levylab.oxford:OxfordVRM",
    "Inst.TC.CF.lvclass": "flex_drivers_levylab.tc:TC_CF",
    "Inst.TC.MNK.lvclass": "flex_drivers_levylab.tc:TC_MNK",
    "Instrument.Aerotech.lvclass": "flex_drivers_levylab.aerotech:Aerotech",
}
