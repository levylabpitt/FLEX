"""
Sets Insertion -> Take Photocurrent Data
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

# %% Experiment variables and functions
def read_CEJSON():
    json_path = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'Control Experiment', 'Control Experiment.json')
    keys = ["User", "Device", "Device Path", "Device Description", "Instrument"]
    with open(json_path, 'r') as file:
        experiment_data = json.load(file)['Experiment']
        subset = {k: experiment_data.get(k) for k in keys if k in experiment_data}
        return subset
        
device_folder = read_CEJSON()['Device Path']


#%% - Experiment
def insertion_sweep(start, stop, step, file_suffix, lockin_measure_channel=1, wait_time = 0.1, save_path=None, notes=None, plot=False):
    """
    Sweep the insertion from start to stop with a given step size.
    """
    insertion = np.arange(start, stop, step)
    signal = []

    for i in tqdm(insertion, desc="Scanning insertion..."):
        dscan.set_insertion(i)
        time.sleep(wait_time)
        signal.append(lockin.get_lockin_result(lockin_measure_channel, 'Mean'))

    # Saving to a file
    filename = f"{time.strftime('%H%M%S')}_{file_suffix}.txt"
    file_path = os.path.join(save_path, filename)
    combined_array = np.column_stack((insertion, signal))
    np.savetxt(file_path, combined_array, delimiter='\t', header='Insertion (mm),Photocurrent (A)')

    # Saving metadata
    if notes:
        notes = \
            f"""
            This is a test script for the DScan and MCLockin instruments.
            """
        with open(f"{file_path}_notes.txt", "w") as file:
            file.write(notes)
    
    if plot:
        plt.plot(insertion, signal)
        plt.xlabel('Insertion (mm)')
        plt.ylabel('Photocurrent (A)')
        plt.show()

    return insertion, signal

def insertion_sweep_custom(start, stop, step, file_suffix, lockin_measure_channel=1, wait_time = 0.1, save_path=None, notes=None, plot=False):
    """
    Sweep the insertion from start to stop with a given step size.
    """
    insertion = np.arange(start, stop, step)
    signal, signal_2 = [], []

    for i in tqdm(insertion, desc="Scanning insertion..."):
        dscan.set_insertion(i)
        time.sleep(wait_time)
        signal.append(lockin.get_lockin_result(lockin_measure_channel, 'Mean'))
        signal_2.append(lockin.get_lockin_result(6, 'Mean'))

    # Saving to a file
    filename = f"{time.strftime('%H%M%S')}_{file_suffix}.txt"
    file_path = os.path.join(save_path, filename)
    combined_array = np.column_stack((insertion, signal, signal_2))
    np.savetxt(file_path, combined_array, delimiter='\t', header='Insertion (mm),Photocurrent_Ch1(A),Photocurrent_Ch2(A)')

    # Saving metadata
    if notes:
        notes = \
            f"""
            This is a test script for the DScan and MCLockin instruments.
            """
        with open(f"{file_path}_notes.txt", "w") as file:
            file.write(notes)
    
    if plot:
        plt.plot(insertion, signal, color='blue')
        plt.plot(insertion, signal_2, color='red')

        plt.xlabel('Insertion (mm)')
        plt.ylabel('Photocurrent (A)')
        plt.show()

    return insertion, signal, signal_2
#%% Experiment
experiment_folder = r'PCvInsertion_Sweeps'
exp_save_path = os.path.join(device_folder, experiment_folder)
if not os.path.exists(exp_save_path):
    os.makedirs(exp_save_path)


# ins_a, pv_a, pv_a2 = insertion_sweep_custom(start=0, 
#                               stop=90, 
#                               step=0.5, 
#                               file_suffix=f"100mBias_T6K_fullrange_cep3", 
#                               lockin_measure_channel=3,
#                               wait_time=0.1, 
#                               save_path=exp_save_path,
#                               plot=True)

ins_a, pv_a = insertion_sweep(start=0, 
                              stop=90, 
                              step=0.2, 
                              file_suffix=f"100mBias_T6K_filter800LP", 
                              lockin_measure_channel=6,
                              wait_time=0.1, 
                              save_path=exp_save_path,
                              plot=True)
#%% Close Instruments
lockin.close()
dscan.disconnect()

# %%
