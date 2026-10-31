"""Data file writers: HDF5 (default) and TDMS (``[tdms]`` extra), each imported when resolved."""

WRITERS: dict[str, str] = {
    "hdf5": "flex.datatypes.hdf5:HDF5Writer",
    "tdms": "flex.datatypes.tdms:TDMSWriter",
}
