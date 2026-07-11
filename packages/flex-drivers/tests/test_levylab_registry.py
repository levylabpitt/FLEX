"""CATALOG / lvclass_registry() integrity tests."""

from flex.components import load_ref
from flex_drivers.levylab import CATALOG, lvclass_registry
from flex_protocols import ZMQInstrument


def test_catalog_names_are_namespaced():
    assert CATALOG
    assert all(name.startswith("levylab.") for name in CATALOG)


def test_catalog_refs_resolve_to_zmq_instruments():
    for name, ref in CATALOG.items():
        cls = load_ref(ref)
        assert isinstance(cls, type), f"{name}: {ref} is not a class"
        assert issubclass(cls, ZMQInstrument), f"{name}: {ref} is not a ZMQInstrument"


def test_lvclass_registry_derived_from_driver_classes():
    registry = lvclass_registry()
    assert registry["Instrument.Lockin.lvclass"] == "flex_drivers.levylab.lockin:Lockin"
    # the five v1 PPMS variants all resolve to the one consolidated driver
    ppms_ref = "flex_drivers.levylab.ppms:PPMS"
    for lvclass in (
        "instrument.PPMS.lvclass",
        "instrument.PPMS1.lvclass",
        "instrument.PPMS2.lvclass",
        "instrument.PPMS3.lvclass",
        "instrument.PPMS-W-1.lvclass",
    ):
        assert registry[lvclass] == ppms_ref
    # TransportServer has no LabVIEW class and must not appear
    assert "flex_drivers.levylab.transport_server:TransportServer" not in registry.values()


def test_every_catalog_class_with_lv_class_is_discoverable():
    registry = lvclass_registry()
    registered = set(registry.values())
    for name, ref in CATALOG.items():
        cls = load_ref(ref)
        if cls.lv_class is not None:
            assert ref in registered, f"{name} ({cls.lv_class}) missing from lvclass_registry()"
