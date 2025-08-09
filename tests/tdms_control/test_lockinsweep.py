#%%
from flex.inst import MCLockin

lockin = MCLockin()

#%%
data = lockin._send_command('getSweepResults')['result']
channel_data = {}

for j in ["AO", "AI"]:
    for i in data[j]:
        channel_name = f'{j}{i["attributes"][f"{j} Channel"]}'
        channel_data[channel_name] = i['Y']

for j in ["X", "Y"]:
    for i in data[j]:
        channel_name = f'AI{i['attributes']['AI Channel']}{j}{i['attributes']['Reference Channel']}'
        channel_data[channel_name] = i['Y']


from nptdms import TdmsWriter, ChannelObject

data = {"Data.000000": channel_data}

with TdmsWriter("example_file.tdms") as tdms_writer:
    for group, channels in data.items():
        tdms_writer.write_segment([
            ChannelObject(group, name, values)
            for name, values in channels.items()
        ])


#%%
lockin.close()