"""Every CATALOG reference must resolve to an Instrument subclass."""

import pytest

from flex.components import load_ref
from flex.instrument import Instrument
from flex_drivers import CATALOG


def test_catalog_is_populated():
    assert CATALOG


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_catalog_ref_resolves_to_instrument(name):
    cls = load_ref(CATALOG[name])
    assert isinstance(cls, type)
    assert issubclass(cls, Instrument)
