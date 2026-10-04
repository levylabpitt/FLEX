from nptdms import TdmsWriter, RootObject, ChannelObject
import numpy as np


def write_tdms(save_path, data_dict, properties=None):

    data = {
        "Data.000000": data_dict
    }

    with TdmsWriter(save_path) as tdms_writer:

        # Root properties
        if properties:
            tdms_writer.write_segment([
                RootObject(properties=properties)
            ])

        # Channels
        for group, channels in data.items():
            tdms_writer.write_segment([
                ChannelObject(group, name, values)
                for name, values in channels.items()
            ])


def write_acquisition_tdms(
    save_path,
    acquisition,
    properties=None,
    **custom_values
):
    """
    Save acquisition waveforms to TDMS.

    properties:
        Root-level TDMS metadata.

    custom_values:
        Additional scalar or array channels.
    """

    first_channel = next(
        (
            acquisition[group][0]
            for group in ("AO", "AI", "X", "Y")
            if group in acquisition and acquisition[group]
        ),
        None
    )

    if first_channel is None:
        raise ValueError("Acquisition contains no waveform data.")

    dt = float(first_channel["dt"])
    n_samples = len(first_channel["Y"])

    # Time
    data_dict = {
        "Time": np.arange(n_samples, dtype=np.float64) * dt
    }

    # Custom values
    for name, value in custom_values.items():

        if np.isscalar(value):
            data_dict[name] = np.array(
                [value],
                dtype=np.float64
            )
        else:
            data_dict[name] = np.asarray(
                value,
                dtype=np.float64
            )

    # Acquisition waveforms
    for group in ("AO", "AI", "X", "Y"):

        for i, channel in enumerate(
            acquisition.get(group, []),
            start=1
        ):
            values = np.asarray(
                channel["Y"],
                dtype=np.float64
            )

            if len(values) != n_samples:
                raise ValueError(
                    f"{group}{i} contains {len(values)} samples; "
                    f"expected {n_samples}."
                )

            data_dict[f"{group}{i}"] = values

    write_tdms(
        save_path,
        data_dict,
        properties=properties
    )