# %% - Test CESession
from flex.exp.CESession import CESession
exp = CESession()


# %% - Testing Context Manager approach
with CESession(timeout=5.0, verbose=True) as myexp:
    # Everything inside this block is "safe"
    print(myexp.DAQ.help())
    
# Instruments are closed automatically here!
# %%
exp.Temperature.help()
exp.Transport.help()
exp.close_all()

#%%
from flex.inst.levylab.Lockin import Lockin
from flex.inst.levylab.TransportServer import Transport
lockin = Lockin()
transport = Transport()

# IV
exp_folder   = f"05 - Sweep T BG\\IV"
exp_comments = f"""									
I+/-: 27/3 1mV 13Hz
V1+/-: 1/2 Diff Ch1
V2+/-: 26/5 Diff Ch6
Sweep T from 0.05K to 1.1K, step 0.05K, 0.05K/min, 1mK Tol, 
Run lockin time for 30s
"""
transport.setExptFolder(exp_folder)
transport.setExptComments(exp_comments)
sweep_config = {'sweepTime': 30, # seconds
        'initialWaitTime': 1, # seconds
        'returnToStart': False,
        'sweepChannels': [{'Enable?': True,
                            'Channel': 1,
                            'Start': 0,
                            'End': 0.001,
                            'Pattern': 'Table',
                            'Table': [{'Channel':1, 'Table':[1,2,3]}]}
                            # add more channels here if needed
                            ]}
transport.LockinSweep(exp_folder,exp_comments,sweep_config)
# transport.LockinSweep(exp_folder,exp_comments,sweep_config)
# %%
from flex.tdms.flexTDMS import write_tdms
import numpy as np

sample_data = {
    "VNA_Array": np.linspace(0, 10, 100),
    "Temperature": np.sin(np.linspace(0, 10, 100)),
    "Pressure": np.cos(np.linspace(0, 10, 100))
}
write_tdms("example_file.tdms", sample_data)
# %%
