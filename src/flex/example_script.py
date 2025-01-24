#%%
from flex.inst import *
from flex.exp import script_to_db
import time
import numpy as np
import matplotlib.pyplot as plt

# Initialize Instruments
ppms = PPMS("tcp://localhost:29270")
lockin = MCLockin("tcp://localhost:29170")

#%% experiment
# Define Parameters
channel_source = 1
channel_drain = 1
channel_gate = 2
channel_Ref = 1
temp_list = np.linspace(300,320,2)
field_list = np.linspace(-1,1,2)
V_list = np.linspace(0,0.1,500)
lockin_wait_time = 1

#%%
# Define Experiment
start_time = time.time()
for field in field_list:
    ppms.set_field(field, 10)
    for temp in temp_list:
        ppms.set_temp(temp, 50)
        current = []
        lockin.setAO_DC(channel_gate,V_list[0])
        time.sleep(lockin_wait_time)
        for V in V_list:
            lockin.setAO_DC(channel_gate, V)
            time.sleep(0.01)
            current.append(lockin.getResults(channel_drain,'X',channel_Ref))
        
        # plotting
        plt.plot(V_list, current)
        plt.title(f'SimWG IV (B={field} T, T={temp} K)')
        plt.xlabel('Voltage (V)')
        plt.ylabel('Drain Lockin X (V)')
        plt.show()
end_time = time.time()
print(f'Experiment finished in {end_time - start_time} seconds')