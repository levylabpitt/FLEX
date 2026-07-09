"""CATALOG / LVCLASS_REGISTRY integrity tests."""

from flex.components import load_ref
from flex_drivers_levylab import CATALOG, LVCLASS_REGISTRY
from flex_protocols import ZMQInstrument


def test_catalog_names_are_namespaced():
    assert CATALOG
    assert all(name.startswith("levylab.") for name in CATALOG)


def test_catalog_refs_resolve_to_zmq_instruments():
    for name, ref in CATALOG.items():
        cls = load_ref(ref)
        assert isinstance(cls, type), f"{name}: {ref} is not a class"
        assert issubclass(cls, ZMQInstrument), f"{name}: {ref} is not a ZMQInstrument"


def test_lvclass_registry_refs_match_lv_class():
    for lvclass, ref in LVCLASS_REGISTRY.items():
        cls = load_ref(ref)
        assert issubclass(cls, ZMQInstrument), f"{lvclass}: {ref} is not a ZMQInstrument"
        aliases = getattr(cls, "lv_class_aliases", ())
        assert cls.lv_class == lvclass or lvclass in aliases, (
            f"{lvclass} resolves to {cls.__name__} whose lv_class is {cls.lv_class!r}"
        )


def test_every_catalog_class_with_lv_class_is_discoverable():
    registered = set(LVCLASS_REGISTRY.values())
    for name, ref in CATALOG.items():
        cls = load_ref(ref)
        if cls.lv_class is not None:
            assert ref in registered, f"{name} ({cls.lv_class}) missing from LVCLASS_REGISTRY"
