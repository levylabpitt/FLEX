from nptdms import TdmsWriter, ChannelObject
import numpy as np

data = {
    "Data.000000": {
        "Time": np.linspace(0, 10, 100),
        "Temperature": np.sin(np.linspace(0, 10, 100))
    }
}

with TdmsWriter("example_file.tdms") as tdms_writer:
    for group, channels in data.items():
        tdms_writer.write_segment([
            ChannelObject(group, name, values)
            for name, values in channels.items()
        ])