#%%  General imports
import matplotlib.pyplot as plt
import numpy as np

# Instrument initialization
from flex.inst import *
from flex.db import db_dataviewer as dv

lockin = MCLockin()
ppms = PPMS()
kh = KH7008()

# %% Experiment 1 - LI Signal vs. Gate
lockin.setAO_Amplitude(1, 0.1)
sweep_config = {
    "sweep_channel" : 2,
    "sweep_start" : 0,
    "sweep_stop" : 0.1,
    "duration" : 20,
    "measure_channel" : 1,
    "ref_channel" : 1
}
# lockin.sweep1d(sweep_config)

time_range= ('2025-04-03 18:14:20-0400',
             '2025-04-03 18:14:44-0400')
dv.plot_sweep1d(time_range, sweep_config)

# %% Experiment 2 - LI Signal vs. Gate vs. Temp
temps = np.linspace(250, 270, 2)
temp_rate = 200
lockin.setAO_Amplitude(1, 0.1)
data = []
for temp in temps:
    ppms.setTemperatureAndWait(temp, temp_rate)
    x,y = lockin.sweep1d(2, 0, 0.1, 20, 1)
    data.append(y)
data_array = np.array(data)

plt.figure()
plt.imshow(data_array, aspect='auto', origin='lower', 
           extent=[x[0], x[-1], temps[0], temps[-1]])
plt.colorbar(label='Lock-in Signal')
plt.xlabel('Sweep Voltage (V)')
plt.ylabel('Temperature (K)')
plt.show()

# %% Close instruments
lockin.close()
ppms.close()
