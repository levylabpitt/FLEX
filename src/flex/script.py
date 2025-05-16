# %% - FLEX Imports
from flex.exp import Experiment
from flex.inst import *
import numpy as np

#%% - Define Experiment and Instruments
exp = Experiment(user="pubudu.wijesinghe", notes='Au Nanorod 2.0')
lockin: MCLockin = exp.init(MCLockin, name="lockin", address='tcp://localhost:29170')
ppms: PPMS = exp.init(PPMS, name="ppms")
# kh = KH7008()

#%% - Define Measurement
with exp.new_measurement("PV vs. Insertion") as meas:
    sweep_config = {
        "sweep_channel": 2,
        "sweep_start": 0,
        "sweep_stop": 0.1,
        "duration": 50,
        "measure_channel": 1,
        "ref_channel": 1
    }
    lockin.sweep1d(sweep_config, plot_data=True)
    lockin.setState('stop')

#%% - Define Multi-instrument Measurement
temp_list = np.arange(300, 400, 50)
b_list = np.arange(-1, 1, 1)
with exp.new_measurement("Multi-instrument") as meas:
    for temp in temp_list:
        ppms.setTemperatureAndWait(float(temp), rate=100)
        for b in b_list:
            ppms.setMagnetAndWait(float(b), rate=5)
            t_range = lockin.sweep1d(sweep_config, plot_data=True)
data = ppms.get_temp_from_db('2025-05-09 07:00:08.638105', '2025-05-09 07:30:00.543921')
print(data)

#%% - End Experiment
exp.end()