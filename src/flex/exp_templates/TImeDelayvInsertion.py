"""
Sets Insertion -> Take TimeDelay Scan
"""

#%% Imports
from flex.inst import *
import time
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from tqdm import tqdm
import os
import json
matplotlib.style.use('ggplot')

#%% Initialize Instruments
lockin = MCLockin()
dscan = DScan("DM240913")
transport = Transport()

# %% Experiment variables and functions
def read_CEJSON():
    json_path = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'Control Experiment', 'Control Experiment.json')
    keys = ["User", "Device", "Device Path", "Device Description", "Instrument"]
    with open(json_path, 'r') as file:
        experiment_data = json.load(file)['Experiment']
        subset = {k: experiment_data.get(k) for k in keys if k in experiment_data}
        return subset
        
device_folder = read_CEJSON()['Device Path']

#%% Experiment
def run_timedelay(exp_folder='flex_timedelay', notes= '', scan_param_name = '', scan_param_val=None):
    experiment_folder = r'99'
    notes = ''
    insertion = dscan.get_insertion()   
    transport.setExptFolder(experiment_folder)
    transport.setExptComments(notes)
    transport.setExptParam('Insertion', insertion)
    transport.startTransport('LockinTimeDelay')
    while transport.getStatus() != 'idle':
        time.sleep(1)
    transport.stopTransport()

exp_folder = r'99'
insertion_array = np.arange(0, 90, 0.1)
for insertion in insertion_array:
    dscan.set_insertion(insertion)
    ins = dscan.get_insertion()
    run_timedelay(exp_folder=exp_folder, notes=f'Insertion={ins}', scan_param_name='Insertion', scan_param_val=ins)


#%% Close Instruments
lockin.close()      
transport.close()
dscan.disconnect()
# %%
