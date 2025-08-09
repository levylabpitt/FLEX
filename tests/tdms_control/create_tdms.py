# import numpy as np
# from nptdms import TdmsWriter, ChannelObject

# # Create dummy data
# time_data = np.linspace(0, 10, 100, dtype=np.float64)
# temperature_data = np.sin(time_data)
# pressure_data = np.cos(time_data)

# with TdmsWriter("example_file.tdms") as tdms_writer:
#     # Group 1 channels
#     tdms_writer.write_segment([
#         ChannelObject("Group 1", "Time", time_data),
#         ChannelObject("Group 1", "Temperature", temperature_data)
#     ])
    
#     # Group 2 channels
#     tdms_writer.write_segment([
#         ChannelObject("Group 2", "Time", time_data),
#         ChannelObject("Group 2", "Pressure", pressure_data)
#     ])

# print("TDMS file created successfully!")



from nptdms import TdmsWriter, ChannelObject
import numpy as np

data = {
    "Group 1": {
        "Time": np.linspace(0, 10, 100),
        "Temperature": np.sin(np.linspace(0, 10, 100))
    },
    "Group 2": {
        "Time": np.linspace(0, 10, 100),
        "Pressure": np.cos(np.linspace(0, 10, 100))
    }
}

with TdmsWriter("example_file.tdms") as tdms_writer:
    for group, channels in data.items():
        tdms_writer.write_segment([
            ChannelObject(group, name, values)
            for name, values in channels.items()
        ])