"""FLEX measurement data file writers.

Concrete :class:`~flex.data.writer.DataWriter` implementations: HDF5 (the
zero-config default) and TDMS (LabVIEW-compatible). Each format is its own
module, imported only when actually resolved; both dependencies (``h5py``
and ``npTDMS``) are installed with the package.
"""

from __future__ import annotations

__version__ = "2.0.0a1"

#: Writer name -> "module:Class" reference (resolved with flex.components.load_ref).
WRITERS: dict[str, str] = {
    "hdf5": "flex_datatypes.hdf5:HDF5Writer",
    "tdms": "flex_datatypes.tdms:TDMSWriter",
}

__all__ = ["WRITERS"]
