import pytest

from flex.ecosystem import FlexConfig


@pytest.fixture
def config(tmp_path):
    """A self-contained config: SQLite + HDF5 + local files under tmp_path."""
    return FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
