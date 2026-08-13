import pytest

from flex import components
from flex.instrument import SimulatedInstrument


def test_available_merges_installed_registries():
    drivers = components.available("drivers")
    assert "levylab.lockin" in drivers


def test_resolve_by_short_name():
    cls = components.resolve("db", "sqlite")
    assert cls.__name__ == "SQLiteStore"


def test_resolve_missing_names_provider():
    with pytest.raises(components.ComponentError, match="flex-nextcloud"):
        # force the "not installed" path even when flex-nextcloud is present
        components._PROVIDERS["storage:definitely-missing"] = "flex-nextcloud"
        try:
            components.resolve("storage", "definitely-missing")
        finally:
            del components._PROVIDERS["storage:definitely-missing"]


def test_resolve_driver_accepts_module_class_ref():
    cls = components.resolve_driver("flex.instrument:SimulatedInstrument")
    assert cls is SimulatedInstrument


def test_resolve_driver_by_catalog_name():
    cls = components.resolve_driver("levylab.lockin")
    assert cls.__name__ == "Lockin"
