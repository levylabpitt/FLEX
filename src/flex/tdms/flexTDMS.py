from nptdms import TdmsWriter, ChannelObject
import numpy as np


def write_tdms(save_path, data_dict):
    data = {
        "Data.000000": data_dict
    }

    with TdmsWriter(save_path) as tdms_writer:
        for group, channels in data.items():
            tdms_writer.write_segment([
                ChannelObject(group, name, values)
                for name, values in channels.items()
            ])

if __name__ == "__main__":
    sample_data = {
        "Time": np.linspace(0, 10, 100),
        "Temperature": np.sin(np.linspace(0, 10, 100)),
        "Pressure": np.cos(np.linspace(0, 10, 100))
    }
    write_tdms("example_file.tdms", sample_data)